#include "native_format.h"

#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <numeric>
#include <openssl/sha.h>
#include <set>
#include <sstream>
#include <sys/resource.h>
#include <unordered_set>
#include <vector>

namespace {
using namespace z0b;

enum class State : uint8_t { Empty, Open, Closed, Full };
struct Slot { uint32_t page; uint32_t version; uint16_t role; uint8_t valid; uint8_t kind; };
struct Zone { State state = State::Empty; uint32_t live = 0; std::vector<Slot> slots; };
struct Page {
  Key key{};
  uint32_t version = 0;
  uint32_t zone = std::numeric_limits<uint32_t>::max();
  uint32_t slot = 0;
  uint32_t page_bytes = 4096;
  uint16_t role = 0;
  bool live = false;
};
struct Marker { uint64_t ordinal=0, seq=0; int64_t page=-1; };
struct Span { uint64_t start=0, end=0; uint32_t count=0; };
struct Cycle {
  uint64_t index=0;
  Marker start{}, last{}, trigger{};
  uint64_t new_blocks=0, app_bytes=0, relocated=0;
  uint32_t capacity=0;
  uint32_t victim=0, destination=0, free_before=0, free_after=0;
  uint64_t live_before=0, invalid_before=0, live_after=0, invalid_after=0;
  std::map<uint16_t,uint64_t> victim_roles;
  std::vector<uint64_t> updates, batches;
};
struct Pending {
  bool active=false;
  Marker start{}, last{};
  uint64_t blocks=0, app_bytes=0;
  std::unordered_set<uint64_t> updates, batches;
};
struct EventAudit {
  uint64_t ordinal=0,seq=0;int64_t page=-1;uint8_t op=0;uint32_t destination=UINT32_MAX;
  uint8_t gc=0;uint32_t victim=UINT32_MAX,moved=0;uint64_t argument=0,update=0,batch=0;
  DeltaAccumulator deltas;
  EventAudit(uint64_t ordinal_value,uint64_t seq_value,int64_t page_value,uint8_t op_value)
      :ordinal(ordinal_value),seq(seq_value),page(page_value),op(op_value){}
};

class Replay {
 public:
  Replay(std::span<const InitialRecord> initial, std::span<const NormalRecord> events,
         std::span<const LifecycleRecord> lifecycle, uint32_t capacity, uint32_t spares,
         std::string placement, uint64_t seed, std::string cleaner)
      : initial_(initial), events_(events), lifecycle_(lifecycle), cap_(capacity), h_(spares),
        placement_(std::move(placement)), seed_(seed), cleaner_(std::move(cleaner)) {
    if (!cap_ || h_ < 2) throw Error("invalid geometry");
    if (cleaner_ != "greedy" && cleaner_ != "oracle") throw Error("bad cleaner");
    load_initial_pages();
    build_placement();
    SHA256_Init(&transition_ctx_);
    static constexpr char domain[]="Z0BTRANSITION1";
    SHA256_Update(&transition_ctx_,domain,sizeof(domain)-1);
    observe_free(0);
    check(true);
  }

  void run() {
    size_t ni=0, li=0;
    while (ni < events_.size() || li < lifecycle_.size()) {
      const bool take_life = li < lifecycle_.size() &&
          (ni == events_.size() || lifecycle_[li].global_seq < events_[ni].global_seq);
      if (li < lifecycle_.size() && ni < events_.size() &&
          lifecycle_[li].global_seq == events_[ni].global_seq) throw Error("write/lifecycle sequence collision");
      ++ordinal_;
      if (take_life) apply_lifecycle(lifecycle_[li++]);
      else apply_write(events_[ni++]);
      observe_free(ordinal_);
    }
    close_free_span(ordinal_);
    check(false);
  }

  void write_json(std::ostream& out, std::string_view engine) const {
    const uint64_t allocated = new_blocks_ * 4096ULL;
    const uint64_t relocated = relocated_blocks_ * 4096ULL;
    out << "{\n  \"schema\":\"zns-ann-z0b-native-replay-v1\",\n"
        << "  \"engine\":\"" << engine << "\",\n  \"status\":\"pass\",\n"
        << "  \"sequence_only\":true,\n  \"temporal_fields_used\":false,\n"
        << "  \"placement\":\"" << json_escape(placement_) << "\",\n"
        << "  \"random_seed\":" << seed_ << ",\n  \"cleaner\":\"" << cleaner_ << "\",\n"
        << "  \"geometry\":{\"zone_capacity_blocks\":" << cap_ << ",\"host_spare_zones\":" << h_
        << ",\"ordinary_initial_zones\":" << ordinary_ << ",\"total_zones\":" << zones_.size() << "},\n"
        << "  \"initial_image\":{\"logical_bytes\":" << initial_logical_bytes_
        << ",\"allocated_bytes\":" << initial_blocks_ * 4096ULL
        << ",\"page_count\":" << initial_blocks_ << "},\n"
        << "  \"bytes\":{\"application_returned_bytes\":" << app_bytes_
        << ",\"normalized_fragment_bytes\":" << fragment_bytes_
        << ",\"allocated_append_bytes\":" << allocated
        << ",\"replacement_rmw_read_bytes\":" << rmw_bytes_
        << ",\"new_page_zero_fill_bytes\":" << zero_bytes_
        << ",\"relocation_allocated_bytes\":" << relocated << "},\n"
        << "  \"host_wa_fraction\":\"" << (new_blocks_ + relocated_blocks_) << "/" << new_blocks_ << "\",\n"
        << "  \"reset_count\":" << resets_ << ",\n"
        << "  \"complete_cycle_count\":" << cycles_.size() << ",\n"
        << "  \"tail\":{\"complete_cycle\":false,\"allocated_new_blocks\":" << pending_.blocks
        << ",\"allocated_append_bytes\":" << pending_.blocks * 4096ULL
        << ",\"application_returned_bytes\":" << pending_.app_bytes << "},\n"
        << "  \"victim_sequence\":[";
    for (size_t i=0;i<victims_.size();++i) { if(i) out<<','; out<<victims_[i]; }
    out << "],\n  \"free_zone_rle\":[";
    for (size_t i=0;i<free_spans_.size();++i) { if(i) out<<','; const auto&s=free_spans_[i];
      out << "{\"start_event\":"<<s.start<<",\"end_event\":"<<s.end<<",\"free_zones\":"<<s.count<<'}'; }
    out << "],\n  \"cycles\":[";
    for (size_t i=0;i<cycles_.size();++i) { if(i) out<<','; emit_cycle(out,cycles_[i]); }
    out << "],\n  \"final_state_sha256\":\"" << final_digest() << "\",\n  \"transition_rolling_sha256\":\""<<transition_digest()<<"\",\n  \"comparable_result\":";
    emit_comparable(out);
    out << "\n}\n";
  }

  size_t page_count() const { return pages_.size(); }
  size_t zone_count() const { return zones_.size(); }

 private:
  std::span<const InitialRecord> initial_;
  std::span<const NormalRecord> events_;
  std::span<const LifecycleRecord> lifecycle_;
  uint32_t cap_, h_, ordinary_=0;
  std::string placement_;
  uint64_t seed_;
  std::string cleaner_;
  std::vector<Page> pages_;
  std::unordered_map<Key,uint32_t,KeyHash> ids_;
  std::unordered_map<uint64_t,std::vector<uint32_t>> object_pages_;
  std::vector<Zone> zones_;
  std::set<uint32_t> free_;
  int64_t current_=-1;
  uint64_t ordinal_=0, initial_blocks_=0, initial_logical_bytes_=0, new_blocks_=0, relocated_blocks_=0, erased_blocks_=0, resets_=0;
  uint64_t app_bytes_=0, fragment_bytes_=0, rmw_bytes_=0, zero_bytes_=0;
  Marker previous_{};
  bool have_previous_=false;
  Pending pending_;
  std::vector<Cycle> cycles_;
  std::vector<uint32_t> victims_;
  std::vector<Span> free_spans_;
  SHA256_CTX transition_ctx_{};
  std::vector<unsigned char> audit_chunk_;

  void load_initial_pages() {
    ids_.reserve(static_cast<size_t>(initial_.size()*1.35)+1024);
    pages_.reserve(initial_.size()+1024);
    const InitialRecord* prior=nullptr;
    for (const auto& rec:initial_) {
      if (!rec.page_bytes || rec.page_bytes>4096 || rec.aligned_offset%4096 || rec.reserved) throw Error("bad initial record");
      if (prior && !key_less(*prior,rec)) throw Error("initial manifest is not strict canonical order");
      prior=&rec;
      Key key{rec.object_incarnation,rec.aligned_offset};
      uint32_t id=static_cast<uint32_t>(pages_.size());
      if (!ids_.emplace(key,id).second) throw Error("duplicate initial page");
      pages_.push_back(Page{key,0,0,0,rec.page_bytes,rec.role,true});
      initial_logical_bytes_ += rec.page_bytes;
      object_pages_[key.object].push_back(id);
    }
    initial_blocks_=pages_.size();
  }

  std::array<unsigned char,32> random_rank(uint32_t id) const {
    const auto& p=pages_[id];
    std::string input="z0b-random-packing-v1";
    input.push_back('\0'); input+=std::to_string(seed_); input.push_back('\0');
    input+=std::to_string(p.key.object); input.push_back(':'); input+=std::to_string(p.key.offset);
    std::array<unsigned char,32> digest{};
    SHA256(reinterpret_cast<const unsigned char*>(input.data()),input.size(),digest.data());
    return digest;
  }

  void build_placement() {
    std::vector<uint32_t> order(pages_.size()); std::iota(order.begin(),order.end(),0);
    if (placement_=="random") {
      struct Ranked { std::array<unsigned char,32> rank; uint32_t id; };
      std::vector<Ranked> ranked; ranked.reserve(order.size());
      for(uint32_t id:order) ranked.push_back({random_rank(id),id});
      std::sort(ranked.begin(),ranked.end(),[&](const Ranked&a,const Ranked&b){
        if(a.rank!=b.rank)return a.rank<b.rank;
        const auto&x=pages_[a.id]; const auto&y=pages_[b.id];
        return std::tie(x.role,x.key.object,x.key.offset)<std::tie(y.role,y.key.object,y.key.offset);
      });
      for(size_t i=0;i<order.size();++i)order[i]=ranked[i].id;
    } else if (placement_=="oracle") {
      std::vector<uint32_t> count(pages_.size(),0);
      for(const auto&e:events_){auto it=ids_.find(Key{e.object_incarnation,e.aligned_offset}); if(it!=ids_.end()&&count[it->second]!=UINT32_MAX)++count[it->second];}
      std::sort(order.begin(),order.end(),[&](uint32_t a,uint32_t b){
        if(count[a]!=count[b])return count[a]>count[b];
        const auto&x=pages_[a];const auto&y=pages_[b];
        return std::tie(x.role,x.key.object,x.key.offset)<std::tie(y.role,y.key.object,y.key.offset);
      });
    } else if (placement_!="canonical" && placement_!="role") throw Error("bad placement");

    uint16_t last_role=0; bool have_role=false;
    for(uint32_t id:order){
      const uint16_t role=pages_[id].role;
      if(zones_.empty() || zones_.back().slots.size()==cap_ ||
         (placement_=="role" && have_role && role!=last_role && !zones_.back().slots.empty())) {
        if(!zones_.empty()) zones_.back().state=zones_.back().slots.size()==cap_?State::Full:State::Closed;
        zones_.push_back(Zone{}); zones_.back().slots.reserve(std::min<uint64_t>(cap_,pages_.size()));
      }
      Zone&z=zones_.back(); uint32_t zid=zones_.size()-1, sid=z.slots.size();
      z.slots.push_back(Slot{id,0,role,1,0}); ++z.live;
      pages_[id].zone=zid;pages_[id].slot=sid;
      last_role=role;have_role=true;
    }
    if(zones_.empty()) throw Error("empty initial manifest");
    zones_.back().state=zones_.back().slots.size()==cap_?State::Full:State::Closed;
    ordinary_=zones_.size();
    if(zones_.back().state==State::Closed)current_=zones_.size()-1;
    zones_.resize(zones_.size()+h_);
    for(uint32_t z=ordinary_;z<zones_.size();++z)free_.insert(z);
  }

  Marker marker(uint64_t seq,int64_t page)const{return Marker{ordinal_,seq,page};}
  void order_check(uint64_t seq,int64_t page){Marker m=marker(seq,page);if(!seq||(have_previous_&&std::tie(seq,page)<=std::tie(previous_.seq,previous_.page)))throw Error("non-monotonic event order");previous_=m;have_previous_=true;}
  uint64_t occupied()const{return initial_blocks_+new_blocks_+relocated_blocks_-erased_blocks_;}
  uint64_t global_live()const{uint64_t n=0;for(const auto&z:zones_)n+=z.live;return n;}

  void open_zone(uint32_t zid){auto&z=zones_.at(zid);if(z.state!=State::Empty&&z.state!=State::Closed)throw Error("zone not openable");if(z.state==State::Empty)free_.erase(zid);z.state=State::Open;current_=zid;}
  void finish(uint32_t zid){auto&z=zones_[zid];if(z.slots.size()==cap_){z.state=State::Full;if(current_==zid)current_=-1;}}
  uint32_t choose_victim(uint32_t dest)const{uint32_t best=UINT32_MAX,live=UINT32_MAX;for(uint32_t z=0;z<zones_.size();++z){if(z==dest||static_cast<int64_t>(z)==current_||zones_[z].state!=State::Full)continue;if(zones_[z].live<live||(zones_[z].live==live&&z<best)){best=z;live=zones_[z].live;}}if(best==UINT32_MAX)throw Error("no FULL victim");return best;}

  std::vector<uint64_t> sorted(const std::unordered_set<uint64_t>&s)const{std::vector<uint64_t>v(s.begin(),s.end());std::sort(v.begin(),v.end());return v;}
  void close_cycle(uint32_t victim,uint32_t dest,uint32_t moved,const Marker&trigger,uint32_t free_before,
                   uint64_t live_before,uint64_t invalid_before,const std::map<uint16_t,uint64_t>&roles){
    if(!pending_.active||!pending_.blocks)throw Error("empty fill window");
    Cycle c; c.index=cycles_.size()+1;c.start=pending_.start;c.last=pending_.last;c.trigger=trigger;
    c.new_blocks=pending_.blocks;c.app_bytes=pending_.app_bytes;c.relocated=moved;c.capacity=cap_;c.victim=victim;c.destination=dest;c.free_before=free_before;
    c.free_after=free_.size();c.live_before=live_before;c.invalid_before=invalid_before;
    c.live_after=global_live();c.invalid_after=occupied()-c.live_after;c.victim_roles=roles;
    c.updates=sorted(pending_.updates);c.batches=sorted(pending_.batches);cycles_.push_back(std::move(c));pending_=Pending{};
  }

  void gc(const Marker&trigger,EventAudit&a){if(free_.size()!=1)throw Error("GC requires one reserve");uint32_t dest=*free_.begin();uint32_t victim=choose_victim(dest);auto&src=zones_[victim];uint32_t moved=src.live;if(moved>=cap_)throw Error("no reclaimable victim");a.gc=1;a.victim=victim;a.moved=moved;a.destination=dest;uint64_t live_before=global_live(),invalid_before=occupied()-live_before;std::map<uint16_t,uint64_t>roles;for(const auto&s:src.slots)if(s.valid)++roles[s.role];uint32_t free_before=free_.size();open_zone(dest);auto&dst=zones_[dest];for(uint32_t i=0;i<src.slots.size();++i){auto&s=src.slots[i];if(!s.valid)continue;auto&p=pages_[s.page];if(!p.live||p.zone!=victim||p.slot!=i||p.version!=s.version)throw Error("stale relocation source");uint32_t ds=dst.slots.size();a.deltas.add({p.key.object,p.key.offset,p.version,victim,i,p.version,dest,ds,p.role,1,1,1});dst.slots.push_back(Slot{s.page,s.version,s.role,1,1});++dst.live;s.valid=0;--src.live;p.zone=dest;p.slot=ds;++relocated_blocks_;}if(src.live)throw Error("reset live victim");erased_blocks_+=src.slots.size();src.slots.clear();src.state=State::Empty;free_.insert(victim);++resets_;victims_.push_back(victim);finish(dest);if(current_<0)throw Error("relocation overflow");close_cycle(victim,dest,moved,trigger,free_before,live_before,invalid_before,roles);}
  uint32_t room(const Marker&trigger,EventAudit&a){if(current_>=0){auto&z=zones_[current_];if(z.state==State::Closed)open_zone(current_);if(z.state==State::Open&&z.slots.size()<cap_){a.destination=current_;return current_;}}if(free_.size()>=2){uint32_t z=*free_.begin();open_zone(z);a.destination=z;return z;}if(free_.size()==1){gc(trigger,a);return current_;}throw Error("free pool exhausted");}

  void note(const Marker&m,uint64_t update,uint64_t batch,bool append){if(append&&!pending_.active){pending_.active=true;pending_.start=m;}if(pending_.active){pending_.last=m;if(update)pending_.updates.insert(update);if(batch)pending_.batches.insert(batch);}}
  void apply_write(const NormalRecord&e){order_check(e.global_seq,e.page_index_within_request);if(!e.fragment_bytes||e.fragment_bytes>4096||e.aligned_offset%4096||e.reserved)throw Error("bad normalized event");Marker m=marker(e.global_seq,e.page_index_within_request);EventAudit a{ordinal_,e.global_seq,static_cast<int64_t>(e.page_index_within_request),1};a.argument=e.fragment_bytes;a.update=e.update_id;a.batch=e.batch_id;uint32_t zid=room(m,a);Key key{e.object_incarnation,e.aligned_offset};uint32_t id;auto it=ids_.find(key);bool replacement=it!=ids_.end()&&pages_[it->second].live;if(it==ids_.end()){id=pages_.size();ids_.emplace(key,id);pages_.push_back(Page{key,0,0,0,4096,e.role,false});object_pages_[key.object].push_back(id);}else{id=it->second;}auto&p=pages_[id];uint32_t oldver=p.version,oldzone=p.zone,oldslot=p.slot;uint8_t oldlive=p.live;if(replacement&&p.role!=e.role)throw Error("role changed");uint32_t version=replacement?p.version+1:1;auto&dst=zones_[zid];uint32_t sid=dst.slots.size();dst.slots.push_back(Slot{id,version,e.role,1,2});++dst.live;if(replacement){auto&old=zones_[p.zone].slots[p.slot];if(!old.valid||old.version!=p.version)throw Error("stale overwrite");old.valid=0;--zones_[p.zone].live;rmw_bytes_+=4096-e.fragment_bytes;}else zero_bytes_+=4096-e.fragment_bytes;p.version=version;p.zone=zid;p.slot=sid;p.role=e.role;p.live=true;a.deltas.add({key.object,key.offset,oldver,oldzone,oldslot,version,zid,sid,e.role,oldlive,1,2});++new_blocks_;app_bytes_+=e.fragment_bytes;fragment_bytes_+=e.fragment_bytes;note(m,e.update_id,e.batch_id,true);++pending_.blocks;pending_.app_bytes+=e.fragment_bytes;finish(zid);commit_audit(a);}
  void apply_lifecycle(const LifecycleRecord&e){order_check(e.global_seq,-1);if(e.kind!=1||e.reserved)throw Error("unsupported lifecycle event");Marker m=marker(e.global_seq,-1);EventAudit a{ordinal_,e.global_seq,-1,2};a.argument=e.new_size_bytes;a.update=e.update_id;a.batch=e.batch_id;auto it=object_pages_.find(e.object_incarnation);if(it!=object_pages_.end())for(uint32_t id:it->second){auto&p=pages_[id];if(p.live&&p.key.offset>=e.new_size_bytes){auto&s=zones_[p.zone].slots[p.slot];if(!s.valid)throw Error("stale truncate");a.deltas.add({p.key.object,p.key.offset,p.version,p.zone,p.slot,p.version,p.zone,p.slot,p.role,1,0,3});s.valid=0;--zones_[p.zone].live;p.live=false;}}note(m,e.update_id,e.batch_id,false);commit_audit(a);}

  void observe_free(uint64_t event){uint32_t count=free_.size();if(free_spans_.empty()||free_spans_.back().count!=count){if(!free_spans_.empty())free_spans_.back().end=event?event-1:0;free_spans_.push_back(Span{event,event,count});}else free_spans_.back().end=event;}
  void close_free_span(uint64_t event){if(!free_spans_.empty())free_spans_.back().end=event;}

  void check(bool initial)const{uint64_t occ=0,live=0;uint32_t opens=0;for(uint32_t z=0;z<zones_.size();++z){const auto&zone=zones_[z];if(zone.slots.size()>cap_)throw Error("WP overflow");if(zone.state==State::Empty&&!zone.slots.empty())throw Error("dirty EMPTY");if(zone.state==State::Full&&zone.slots.size()!=cap_)throw Error("short FULL");opens+=zone.state==State::Open;occ+=zone.slots.size();live+=zone.live;}if(opens>1||occ!=occupied())throw Error("zone/account invariant");uint64_t page_live=0;for(uint32_t id=0;id<pages_.size();++id){const auto&p=pages_[id];if(!p.live)continue;++page_live;if(p.zone>=zones_.size()||p.slot>=zones_[p.zone].slots.size()){throw Error("page location range");}const auto&s=zones_[p.zone].slots[p.slot];if(!s.valid||s.page!=id||s.version!=p.version)throw Error("page map mismatch");}if(page_live!=live)throw Error("live count mismatch");if(initial&&free_.size()!=h_)throw Error("initial free count");if(!initial&&free_.empty())throw Error("relocation reserve consumed");}

  static void emit_marker(std::ostream&out,const Marker&m){out<<"{\"event_ordinal\":"<<m.ordinal<<",\"global_seq\":"<<m.seq<<",\"page_index_within_request\":"<<m.page<<'}';}
  static void emit_ranges(std::ostream&out,const std::vector<uint64_t>&v){out<<'[';bool first=true;for(size_t i=0;i<v.size();){size_t j=i;while(j+1<v.size()&&v[j+1]==v[j]+1)++j;if(!first)out<<',';first=false;out<<'['<<v[i]<<','<<v[j]<<']';i=j+1;}out<<']';}
  static void emit_cycle(std::ostream&out,const Cycle&c){out<<"{\"cycle_index\":"<<c.index<<",\"start\":";emit_marker(out,c.start);out<<",\"last_append_before_gc\":";emit_marker(out,c.last);out<<",\"gc_trigger\":";emit_marker(out,c.trigger);out<<",\"allocated_new_blocks\":"<<c.new_blocks<<",\"allocated_new_append_bytes\":"<<c.new_blocks*4096ULL<<",\"application_returned_bytes\":"<<c.app_bytes<<",\"relocated_pages\":"<<c.relocated<<",\"relocation_allocated_bytes\":"<<c.relocated*4096ULL<<",\"host_wa_fraction\":\""<<(c.new_blocks+c.relocated)<<'/'<<c.new_blocks<<"\",\"victim_zone\":"<<c.victim<<",\"relocation_destination\":"<<c.destination<<",\"victim_valid_fraction\":\""<<c.relocated<<'/'<<c.capacity<<"\",\"free_zones_before_gc\":"<<c.free_before<<",\"free_zones_after_reset\":"<<c.free_after<<",\"live_blocks_before\":"<<c.live_before<<",\"live_bytes_before\":"<<c.live_before*4096ULL<<",\"invalid_blocks_before\":"<<c.invalid_before<<",\"invalid_bytes_before\":"<<c.invalid_before*4096ULL<<",\"live_blocks_after\":"<<c.live_after<<",\"live_bytes_after\":"<<c.live_after*4096ULL<<",\"invalid_blocks_after\":"<<c.invalid_after<<",\"invalid_bytes_after\":"<<c.invalid_after*4096ULL<<",\"victim_role_pages\":{";bool f=true;for(auto[k,v]:c.victim_roles){if(!f)out<<',';f=false;out<<'\"'<<k<<"\":"<<v;}out<<"},\"update_id_ranges\":";emit_ranges(out,c.updates);out<<",\"batch_id_ranges\":";emit_ranges(out,c.batches);out<<'}';}
  static void emit_comparable_cycle(std::ostream&out,const Cycle&c){out<<"{\"cycle_index\":"<<c.index<<",\"start\":";emit_marker(out,c.start);out<<",\"last_append_before_gc\":";emit_marker(out,c.last);out<<",\"gc_trigger\":";emit_marker(out,c.trigger);out<<",\"allocated_new_blocks\":"<<c.new_blocks<<",\"allocated_new_append_bytes\":"<<c.new_blocks*4096ULL<<",\"application_returned_bytes\":"<<c.app_bytes<<",\"relocated_pages\":"<<c.relocated<<",\"relocation_allocated_bytes\":"<<c.relocated*4096ULL<<",\"host_wa_fraction\":\""<<(c.new_blocks+c.relocated)<<'/'<<c.new_blocks<<"\",\"victim_zone\":"<<c.victim<<",\"relocation_destination\":"<<c.destination<<",\"victim_valid_fraction\":\""<<c.relocated<<'/'<<c.capacity<<"\",\"free_zones_before_gc\":"<<c.free_before<<",\"free_zones_after_reset\":"<<c.free_after<<",\"victim_role_pages\":{";bool f=true;for(auto[k,v]:c.victim_roles){if(!f)out<<',';f=false;out<<'\"'<<k<<"\":"<<v;}out<<"},\"update_id_ranges\":";emit_ranges(out,c.updates);out<<",\"batch_id_ranges\":";emit_ranges(out,c.batches);out<<'}';}

  void emit_comparable(std::ostream&out)const{out<<"{\"status\":\"pass\",\"sequence_only\":true,\"temporal_fields_used\":false,\"placement\":\""<<json_escape(placement_)<<"\",\"random_seed\":"<<seed_<<",\"cleaner\":\""<<cleaner_<<"\",\"initial_image\":{\"logical_bytes\":"<<initial_logical_bytes_<<",\"allocated_bytes\":"<<initial_blocks_*4096ULL<<",\"page_count\":"<<initial_blocks_<<"},\"bytes\":{\"application_returned_bytes\":"<<app_bytes_<<",\"normalized_fragment_bytes\":"<<fragment_bytes_<<",\"allocated_append_bytes\":"<<new_blocks_*4096ULL<<",\"replacement_rmw_read_bytes\":"<<rmw_bytes_<<",\"new_page_zero_fill_bytes\":"<<zero_bytes_<<",\"relocation_allocated_bytes\":"<<relocated_blocks_*4096ULL<<"},\"host_wa_fraction\":\""<<new_blocks_+relocated_blocks_<<'/'<<new_blocks_<<"\",\"reset_count\":"<<resets_<<",\"complete_cycle_count\":"<<cycles_.size()<<",\"tail\":{\"complete_cycle\":false,\"allocated_new_blocks\":"<<pending_.blocks<<",\"allocated_append_bytes\":"<<pending_.blocks*4096ULL<<",\"application_returned_bytes\":"<<pending_.app_bytes<<"},\"victim_sequence\":[";for(size_t i=0;i<victims_.size();++i){if(i)out<<',';out<<victims_[i];}out<<"],\"cycles\":[";for(size_t i=0;i<cycles_.size();++i){if(i)out<<',';emit_comparable_cycle(out,cycles_[i]);}out<<"],\"final_state_sha256\":\""<<final_digest()<<"\",\"transition_rolling_sha256\":\""<<transition_digest()<<"\"}";}

  void commit_audit(EventAudit&a){
    uint64_t live=global_live(),invalid=occupied()-live,free=free_.size();
    int64_t head=current_;uint8_t state=255;uint64_t wp=0,head_live=0;
    if(current_>=0){const auto&z=zones_[current_];state=static_cast<uint8_t>(z.state);wp=z.slots.size();head_live=z.live;}
    const TransitionAuditRecord record{
      a.ordinal,a.seq,a.page,a.op,a.argument,a.update,a.batch,a.destination,
      a.gc,a.victim,a.moved,a.deltas.count,a.deltas.lo,a.deltas.hi,
      new_blocks_,relocated_blocks_,resets_,app_bytes_,fragment_bytes_,rmw_bytes_,zero_bytes_,
      live,invalid,free,head,state,wp,head_live};
    const auto*first=reinterpret_cast<const unsigned char*>(&record);
    audit_chunk_.insert(audit_chunk_.end(),first,first+sizeof(record));
    if(audit_chunk_.size()>=4*1024*1024){SHA256_Update(&transition_ctx_,audit_chunk_.data(),audit_chunk_.size());audit_chunk_.clear();}
  }
  std::string transition_digest()const{SHA256_CTX copy=transition_ctx_;if(!audit_chunk_.empty())SHA256_Update(&copy,audit_chunk_.data(),audit_chunk_.size());unsigned char d[32];SHA256_Final(d,&copy);std::ostringstream s;for(auto b:d)s<<std::hex<<std::setw(2)<<std::setfill('0')<<static_cast<unsigned>(b);return s.str();}

  std::string final_digest()const{SHA256_CTX ctx;SHA256_Init(&ctx);for(uint32_t id=0;id<pages_.size();++id){const auto&p=pages_[id];SHA256_Update(&ctx,&p.key,sizeof(p.key));SHA256_Update(&ctx,&p.version,sizeof(p.version));SHA256_Update(&ctx,&p.zone,sizeof(p.zone));SHA256_Update(&ctx,&p.slot,sizeof(p.slot));SHA256_Update(&ctx,&p.role,sizeof(p.role));uint8_t live=p.live;SHA256_Update(&ctx,&live,1);}for(uint32_t z:free_)SHA256_Update(&ctx,&z,sizeof(z));unsigned char d[32];SHA256_Final(d,&ctx);std::ostringstream s;for(auto b:d)s<<std::hex<<std::setw(2)<<std::setfill('0')<<static_cast<unsigned>(b);return s.str();}
};

} // namespace

int main(int argc,char**argv){try{auto start=std::chrono::steady_clock::now();Args a(argc,argv);MappedFile im(a.need("initial")),nm(a.need("normalized")),lm(a.need("lifecycle"));auto[ih,initial]=im.records<InitialHeader,InitialRecord>("Z0BMAP1");auto[nh,normal]=nm.records<NormalHeader,NormalRecord>("Z0BNORM1");auto[lh,life]=lm.records<LifecycleHeader,LifecycleRecord>("Z0BLIFE1");if(ih->run_hash!=lh->run_hash)throw Error("run hash mismatch");Replay replay(initial,normal,life,a.u64("capacity-blocks"),a.u64("host-spares"),a.need("placement"),a.u64("random-seed",0,false),a.need("cleaner"));replay.run();std::filesystem::path output=a.need("output");if(std::filesystem::exists(output))throw Error("output exists");auto tmp=output;tmp+=".tmp."+std::to_string(::getpid());std::ofstream out(tmp);if(!out)throw Error("cannot create output");replay.write_json(out,"main");out.close();std::filesystem::rename(tmp,output);auto sec=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();rusage ru{};getrusage(RUSAGE_SELF,&ru);std::cout<<"{\"status\":\"pass\",\"events\":"<<normal.size()+life.size()<<",\"pages\":"<<replay.page_count()<<",\"zones\":"<<replay.zone_count()<<",\"wall_seconds\":"<<sec<<",\"max_rss_kib\":"<<ru.ru_maxrss<<"}\n";return 0;}catch(const std::exception&e){std::cerr<<"z0b_native_replay: "<<e.what()<<'\n';return 1;}}
