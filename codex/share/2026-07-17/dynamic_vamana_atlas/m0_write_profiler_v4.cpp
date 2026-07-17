#include <atomic>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <fcntl.h>
#include <mutex>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/uio.h>
#include <unistd.h>
#include <unordered_map>
#include <vector>

namespace {
constexpr uint64_t kPage = 4096;
enum class Phase : uint8_t { Other, Load, Insert, Delete, Visibility, Publish, Metadata };
const char *phase_name(Phase p) {
  switch (p) {
    case Phase::Load: return "load";
    case Phase::Insert: return "insert_neighbor_repair";
    case Phase::Delete: return "delete";
    case Phase::Visibility: return "visibility";
    case Phase::Publish: return "publish_save";
    case Phase::Metadata: return "metadata";
    default: return "other";
  }
}

struct Identity { uint64_t dev = 0, ino = 0; std::string path; bool valid = false; };
struct Bucket { uint64_t bytes=0, request_touches=0, page_touches=0, fsyncs=0, fdatasyncs=0; };
struct Meta { std::string ledger, entry, component, path; uint64_t dev=0, ino=0; Phase phase=Phase::Other; };
struct PageKey { uint32_t bucket; uint64_t page; bool operator==(const PageKey&o)const{return bucket==o.bucket&&page==o.page;} };
struct PageHash { size_t operator()(const PageKey&v)const{return size_t((v.page^(uint64_t(v.bucket)<<32))*0x9e3779b97f4a7c15ULL);} };
struct Total { uint64_t bytes=0, requests=0; };
struct Role { uint64_t bytes=0, touches=0; std::unordered_map<uint64_t,uint32_t> pages; };
struct State {
  std::mutex mu; std::atomic<uint8_t> phase{uint8_t(Phase::Other)}; std::atomic<bool> flushed{false};
  std::string root, output; std::unordered_map<std::string,uint32_t> ids; std::vector<Meta> metas;
  std::vector<Bucket> buckets; std::unordered_map<PageKey,uint32_t,PageHash> pages;
  std::unordered_map<std::string,Total> totals, entries; std::unordered_map<std::string,Role> roles;
};
State &state(){static State*s=[](){auto*v=new State;if(auto*p=getenv("ATLAS_M0_INDEX_ROOT"))v->root=p;if(auto*p=getenv("ATLAS_M0_PROFILE_OUTPUT"))v->output=p;return v;}();return*s;}
thread_local bool in_hook=false;
template<class T>T next_symbol(const char*n){return reinterpret_cast<T>(dlsym(RTLD_NEXT,n));}
std::string esc(const std::string&s){std::ostringstream o;for(unsigned char c:s){if(c=='\\')o<<"\\\\";else if(c=='\"')o<<"\\\"";else if(c=='\n')o<<"\\n";else if(c<0x20)o<<"?";else o<<c;}return o.str();}
Identity identity(int fd){
  Identity x; struct stat st{}; if(syscall(SYS_fstat,fd,&st)!=0)return x; x.dev=uint64_t(st.st_dev);x.ino=uint64_t(st.st_ino);
  char link[64],buf[4096];snprintf(link,sizeof(link),"/proc/self/fd/%d",fd);ssize_t n=syscall(SYS_readlink,link,buf,sizeof(buf)-1);
  if(n>0){buf[n]=0;x.path=buf;const std::string suffix=" (deleted)";if(x.path.size()>=suffix.size()&&x.path.compare(x.path.size()-suffix.size(),suffix.size(),suffix)==0)x.path.resize(x.path.size()-suffix.size());}
  x.valid=!x.path.empty();return x;
}
bool under_root(const State&s,const std::string&p){return !s.root.empty()&&p.size()>=s.root.size()&&p.compare(0,s.root.size(),s.root)==0&&(p.size()==s.root.size()||p[s.root.size()]=='/');}
std::string basename(const std::string&p){auto q=p.find_last_of('/');return q==std::string::npos?p:p.substr(q+1);}
std::string component(const std::string&p,uint64_t off){
  std::string n=basename(p);
  if(n.find(".tags")!=std::string::npos||n.find("reorder_map")!=std::string::npos||n.find("index_map")!=std::string::npos)return "metadata";
  if(n.find("delete")!=std::string::npos||n.find("tombstone")!=std::string::npos||n.find("journal")!=std::string::npos)return "delete_tombstone";
  if(n.find("disk_index_graph")!=std::string::npos||n.find("nbr")!=std::string::npos)return "graph";
  if(n.find("disk_index_data")!=std::string::npos||n.find("pq_")!=std::string::npos||n.find("vector")!=std::string::npos)return "vector";
  if(n.find("_disk.index")!=std::string::npos)return off<kPage?"metadata":"graph_vector_combined";
  return "unknown/other";
}
uint64_t next_boundary(const std::string&p,uint64_t off,uint64_t end){return basename(p).find("_disk.index")!=std::string::npos&&off<kPage&&end>kPage?kPage:end;}
uint32_t bucket(State&s,const std::string&ledger,const std::string&entry,Phase phase,const std::string&comp,const Identity&id){
  std::string key=ledger+"\n"+entry+"\n"+std::to_string(unsigned(phase))+"\n"+comp+"\n"+std::to_string(id.dev)+"\n"+std::to_string(id.ino);
  auto it=s.ids.find(key);if(it!=s.ids.end())return it->second;uint32_t n=s.buckets.size();s.ids.emplace(key,n);s.metas.push_back({ledger,entry,comp,id.path,id.dev,id.ino,phase});s.buckets.emplace_back();return n;
}
void record(const char*ledger,const char*entry,int fd,uint64_t off,uint64_t len){
  if(!len||in_hook)return;
  in_hook=true;State&s=state();Identity id=identity(fd);if(!id.valid||!under_root(s,id.path)){in_hook=false;return;}
  std::lock_guard<std::mutex>g(s.mu);Phase phase=Phase(s.phase.load(std::memory_order_relaxed));s.totals[ledger].bytes+=len;s.totals[ledger].requests++;s.entries[std::string(ledger)+"\n"+entry].bytes+=len;s.entries[std::string(ledger)+"\n"+entry].requests++;
  uint64_t end=off+len;for(uint64_t pos=off;pos<end;){uint64_t stop=next_boundary(id.path,pos,end);std::string comp=component(id.path,pos);Phase p=phase;if(p!=Phase::Load&&p!=Phase::Publish&&comp=="metadata")p=Phase::Metadata;if(comp=="delete_tombstone")p=Phase::Delete;uint32_t b=bucket(s,ledger,entry,p,comp,id);Bucket&v=s.buckets[b];v.bytes+=stop-pos;v.request_touches++;uint64_t first=pos/kPage,last=(stop-1)/kPage;for(uint64_t page=first;page<=last;++page){++s.pages[{b,page}];++v.page_touches;}pos=stop;}
  in_hook=false;
}
void sync_record(int fd,bool data){if(in_hook)return;in_hook=true;State&s=state();Identity id=identity(fd);if(id.valid&&under_root(s,id.path)){std::lock_guard<std::mutex>g(s.mu);uint32_t b=bucket(s,"posix","fdatasync/fsync",Phase(s.phase.load()),component(id.path,0),id);if(data)++s.buckets[b].fdatasyncs;else++s.buckets[b].fsyncs;}in_hook=false;}
void set_phase(const char*n){if(!n)return;std::string x=n;Phase p=Phase::Other;if(x=="clone_ready"||x=="load")p=Phase::Load;else if(x=="insert"||x=="ingest_begin"||x=="insert_neighbor_repair")p=Phase::Insert;else if(x=="delete")p=Phase::Delete;else if(x=="online_visibility_probe_begin"||x=="visibility")p=Phase::Visibility;else if(x=="publish_begin"||x=="publish_save")p=Phase::Publish;else if(x=="metadata")p=Phase::Metadata;state().phase.store(uint8_t(p));}
void flush(){
  State&s=state();if(s.output.empty()||s.flushed.exchange(true))return;std::lock_guard<std::mutex>g(s.mu);std::vector<uint64_t>unique(s.buckets.size()),rewritten(s.buckets.size()),once(s.buckets.size()),maxw(s.buckets.size());for(auto&e:s.pages){++unique[e.first.bucket];if(e.second==1)++once[e.first.bucket];else++rewritten[e.first.bucket];if(e.second>maxw[e.first.bucket])maxw[e.first.bucket]=e.second;}
  std::ostringstream o;o<<"{\n  \"schema\":\"dynamic-vamana-write-attribution-m0-v4\",\n  \"index_root\":\""<<esc(s.root)<<"\",\n  \"ledger_totals\":{";bool first=true;for(auto&e:s.totals){if(!first)o<<",";first=false;o<<"\n    \""<<esc(e.first)<<"\":{\"requested_bytes\":"<<e.second.bytes<<",\"request_count\":"<<e.second.requests<<"}";}o<<"\n  },\n  \"entry_totals\":[";first=true;for(auto&e:s.entries){auto q=e.first.find('\n');if(!first)o<<",";first=false;o<<"\n    {\"ledger\":\""<<esc(e.first.substr(0,q))<<"\",\"entry\":\""<<esc(e.first.substr(q+1))<<"\",\"requested_bytes\":"<<e.second.bytes<<",\"request_count\":"<<e.second.requests<<"}";}o<<"\n  ],\n  \"buckets\":[";
  for(size_t i=0;i<s.buckets.size();++i){if(i)o<<",";auto&b=s.buckets[i];auto&m=s.metas[i];o<<"\n    {\"ledger\":\""<<esc(m.ledger)<<"\",\"entry\":\""<<esc(m.entry)<<"\",\"phase\":\""<<phase_name(m.phase)<<"\",\"component\":\""<<esc(m.component)<<"\",\"device\":"<<m.dev<<",\"inode\":"<<m.ino<<",\"path\":\""<<esc(m.path)<<"\",\"requested_bytes\":"<<b.bytes<<",\"request_touches\":"<<b.request_touches<<",\"unique_4k_pages\":"<<unique[i]<<",\"page_write_touches\":"<<b.page_touches<<",\"pages_written_once\":"<<once[i]<<",\"pages_rewritten\":"<<rewritten[i]<<",\"max_page_writes\":"<<maxw[i]<<",\"page_rewrite_factor\":"<<(unique[i]?double(b.page_touches)/unique[i]:0.0)<<",\"fsync_count\":"<<b.fsyncs<<",\"fdatasync_count\":"<<b.fdatasyncs<<"}";
  }
  o<<"\n  ],\n  \"logical_roles\":[";first=true;for(auto&e:s.roles){if(!first)o<<",";first=false;uint64_t rw=0,mx=0;for(auto&p:e.second.pages){if(p.second>1)++rw;if(p.second>mx)mx=p.second;}o<<"\n    {\"role\":\""<<esc(e.first)<<"\",\"requested_bytes\":"<<e.second.bytes<<",\"unique_4k_pages\":"<<e.second.pages.size()<<",\"page_write_touches\":"<<e.second.touches<<",\"pages_rewritten\":"<<rw<<",\"max_page_writes\":"<<mx<<",\"page_rewrite_factor\":"<<(e.second.pages.empty()?0.0:double(e.second.touches)/e.second.pages.size())<<"}";}o<<"\n  ]\n}\n";
  std::string data=o.str();int fd=syscall(SYS_openat,AT_FDCWD,s.output.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);if(fd<0)return;size_t done=0;while(done<data.size()){ssize_t n=syscall(SYS_write,fd,data.data()+done,data.size()-done);if(n<=0)break;done+=size_t(n);}syscall(SYS_fsync,fd);syscall(SYS_close,fd);
}
}

extern "C" void m0_set_phase(const char*n){set_phase(n);}
extern "C" void m0_record_async_request(const char*entry,int fd,uint64_t off,uint64_t len){if(entry)record("async",entry,fd,off,len);}
extern "C" void m0_record_role_page(const char*role,uint64_t off,uint64_t len){if(!role||!len||in_hook)return;in_hook=true;State&s=state();std::lock_guard<std::mutex>g(s.mu);auto&r=s.roles[role];r.bytes+=len;uint64_t first=off/kPage,last=(off+len-1)/kPage;for(uint64_t p=first;p<=last;++p){++r.pages[p];++r.touches;}in_hook=false;}
extern "C" ssize_t write(int fd,const void*b,size_t n){using F=ssize_t(*)(int,const void*,size_t);static F f=next_symbol<F>("write");ssize_t r=f(fd,b,n);if(r>0){off_t e=lseek(fd,0,SEEK_CUR);record("posix","write",fd,e>=r?uint64_t(e-r):0,r);}return r;}
extern "C" ssize_t pwrite(int fd,const void*b,size_t n,off_t o){using F=ssize_t(*)(int,const void*,size_t,off_t);static F f=next_symbol<F>("pwrite");ssize_t r=f(fd,b,n,o);if(r>0)record("posix","pwrite",fd,o,r);return r;}
extern "C" ssize_t pwrite64(int fd,const void*b,size_t n,off64_t o){using F=ssize_t(*)(int,const void*,size_t,off64_t);static F f=next_symbol<F>("pwrite64");ssize_t r=f(fd,b,n,o);if(r>0)record("posix","pwrite64",fd,o,r);return r;}
extern "C" ssize_t writev(int fd,const iovec*v,int n){using F=ssize_t(*)(int,const iovec*,int);static F f=next_symbol<F>("writev");ssize_t r=f(fd,v,n);if(r>0){off_t e=lseek(fd,0,SEEK_CUR);record("posix","writev",fd,e>=r?uint64_t(e-r):0,r);}return r;}
extern "C" ssize_t pwritev(int fd,const iovec*v,int n,off_t o){using F=ssize_t(*)(int,const iovec*,int,off_t);static F f=next_symbol<F>("pwritev");ssize_t r=f(fd,v,n,o);if(r>0)record("posix","pwritev",fd,o,r);return r;}
extern "C" int fsync(int fd){using F=int(*)(int);static F f=next_symbol<F>("fsync");int r=f(fd);if(!r)sync_record(fd,false);return r;}
extern "C" int fdatasync(int fd){using F=int(*)(int);static F f=next_symbol<F>("fdatasync");int r=f(fd);if(!r)sync_record(fd,true);return r;}
__attribute__((destructor)) static void fini(){flush();}
