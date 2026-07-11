#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdlib>
#include <csignal>
#include <deque>
#include <execinfo.h>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <mutex>
#include <pthread.h>
#include <sched.h>
#include <string>
#include <thread>
#include <unordered_map>
#include <unistd.h>
#include <vector>

#ifdef P0_DGAI
#include "distance.h"
#include "parameters.h"
#include "v2/dynamic_index.h"
#else
#include "dynamic_index.h"
#endif

namespace {

using Clock = std::chrono::steady_clock;

void crash_trace(int sig) {
  void *frames[64];
  int n = backtrace(frames, 64);
  std::cerr << "fatal_signal=" << sig << " frames=" << n << "\n";
  backtrace_symbols_fd(frames, n, STDERR_FILENO);
  _Exit(128 + sig);
}

uint64_t wall_us() {
  using namespace std::chrono;
  return duration_cast<microseconds>(system_clock::now().time_since_epoch()).count();
}

struct Args {
  std::string index;
  std::string data;
  std::string query;
  std::string truth;
  std::string output;
  std::string run_id;
  double query_qps = 0;
  double update_qps = 0;
  int query_threads = 8;
  int update_threads = 1;
  int warmup_sec = 5;
  int duration_sec = 15;
  uint32_t base_npts = 900000;
  uint32_t L = 160;
  uint32_t R = 64;
  uint32_t beam = 4;
  int strategy = 1;
  int search_mode = 3;
};

Args parse_args(int argc, char **argv) {
  std::unordered_map<std::string, std::string> kv;
  for (int i = 1; i + 1 < argc; i += 2) kv[argv[i]] = argv[i + 1];
  auto get = [&](const std::string &k, const std::string &d = "") {
    auto it = kv.find(k);
    return it == kv.end() ? d : it->second;
  };
  Args a;
  a.index = get("--index");
  a.data = get("--data");
  a.query = get("--query");
  a.truth = get("--truth");
  a.output = get("--output");
  a.run_id = get("--run_id", "p0");
  a.query_qps = std::stod(get("--query_qps", "0"));
  a.update_qps = std::stod(get("--update_qps", "0"));
  a.query_threads = std::stoi(get("--query_threads", "8"));
  a.update_threads = std::stoi(get("--update_threads", "1"));
  a.warmup_sec = std::stoi(get("--warmup_sec", "5"));
  a.duration_sec = std::stoi(get("--duration_sec", "15"));
  a.base_npts = std::stoul(get("--base_npts", "900000"));
  a.L = std::stoul(get("--L", "160"));
  a.R = std::stoul(get("--R", "64"));
  a.beam = std::stoul(get("--beam", "4"));
  a.strategy = std::stoi(get("--strategy", "1"));
  a.search_mode = std::stoi(get("--search_mode", "3"));
  return a;
}

template <class T>
std::vector<T> load_bin(const std::string &path, uint32_t &n, uint32_t &d) {
  std::ifstream in(path, std::ios::binary);
  if (!in) throw std::runtime_error("cannot open " + path);
  in.read(reinterpret_cast<char *>(&n), 4);
  in.read(reinterpret_cast<char *>(&d), 4);
  std::vector<T> out(static_cast<size_t>(n) * d);
  in.read(reinterpret_cast<char *>(out.data()), out.size() * sizeof(T));
  if (!in) throw std::runtime_error("short read " + path);
  return out;
}

struct Truth {
  uint32_t nq = 0;
  uint32_t width = 0;
  std::vector<uint32_t> ids;
};

Truth load_truth(const std::string &path) {
  Truth t;
  std::ifstream in(path, std::ios::binary);
  if (!in) throw std::runtime_error("cannot open " + path);
  in.read(reinterpret_cast<char *>(&t.nq), 4);
  in.read(reinterpret_cast<char *>(&t.width), 4);
  t.ids.resize(static_cast<size_t>(t.nq) * t.width);
  in.read(reinterpret_cast<char *>(t.ids.data()), t.ids.size() * sizeof(uint32_t));
  if (!in) throw std::runtime_error("short truth read");
  return t;
}

void pin_to_cpu(int cpu) {
  cpu_set_t set;
  CPU_ZERO(&set);
  CPU_SET(cpu, &set);
  int rc = pthread_setaffinity_np(pthread_self(), sizeof(set), &set);
  if (rc != 0) std::cerr << "affinity_failed cpu=" << cpu << " rc=" << rc << "\n";
}

template <class T>
class Queue {
 public:
  void push(T v) {
    {
      std::lock_guard<std::mutex> lock(mu_);
      q_.push_back(std::move(v));
    }
    cv_.notify_one();
  }
  bool pop(T &v) {
    std::unique_lock<std::mutex> lock(mu_);
    cv_.wait(lock, [&] { return closed_ || !q_.empty(); });
    if (q_.empty()) return false;
    v = std::move(q_.front());
    q_.pop_front();
    return true;
  }
  size_t size() {
    std::lock_guard<std::mutex> lock(mu_);
    return q_.size();
  }
  void close() {
    {
      std::lock_guard<std::mutex> lock(mu_);
      closed_ = true;
    }
    cv_.notify_all();
  }
 private:
  std::mutex mu_;
  std::condition_variable cv_;
  std::deque<T> q_;
  bool closed_ = false;
};

struct Task {
  uint64_t seq = 0;
  uint64_t due_wall_us = 0;
  Clock::time_point due;
  bool measure = true;
};

struct Row {
  std::string op;
  uint64_t seq = 0;
  int tid = 0;
  uint64_t arrival_us = 0;
  uint64_t start_us = 0;
  uint64_t end_us = 0;
  double queue_us = 0;
  double service_us = 0;
  double total_us = 0;
  double recall = -1;
  double n_ios = 0;
  double io_us = 0;
  uint32_t visible_npts = 0;
  std::string status = "ok";
};

class Adapter {
 public:
  Adapter(const Args &a, uint32_t dim) : args_(a) {
#ifdef P0_DGAI
    params_.Set<unsigned>("L_disk", a.L);
    params_.Set<unsigned>("R_disk", a.R);
    params_.Set<float>("alpha_disk", 1.2);
    params_.Set<unsigned>("C", 160);
    params_.Set<unsigned>("beamwidth", a.beam);
    params_.Set<unsigned>("nodes_to_cache", 0);
    params_.Set<unsigned>("num_threads", std::max(4, a.query_threads + a.update_threads + 2));
    index_dgai_.reset(new pipeann::DynamicSSDIndex<float, uint32_t>(
        params_, a.index, a.index, &dist_, pipeann::Metric::L2, a.search_mode, false, a.strategy));
    // DGAI grows the global PQ byte vector on the first insert. Concurrent
    // readers retain data() pointers, so an in-run reallocation is unsafe.
    // Pre-size to the exact 1.5x growth used by the insert path before workers
    // start; this is capacity preparation only and does not alter PQ codes.
    auto &pq = index_dgai_->_disk_index->data;
    pq.resize(pq.size() + pq.size() / 2);
#else
    params_odin_.L = a.L;
    params_odin_.beam_width = 8;
    params_odin_.max_nthreads = std::max(4, a.query_threads + a.update_threads + 2);
    index_odin_.reset(new DynamicIndex<float>(dim, pipeann::Metric::L2, &params_odin_));
    index_odin_->load(a.index, true);
#endif
  }

  void search(const float *q, uint32_t *ids, float *dists, pipeann::QueryStats &stats) {
#ifdef P0_DGAI
    index_dgai_->search(q, 10, 0, args_.L, args_.beam, ids, dists, &stats, true);
#else
    index_odin_->search(q, 10, args_.L, ids, dists, &stats);
#endif
  }

  void insert(const float *v, uint32_t id) {
#ifdef P0_DGAI
    index_dgai_->insert(v, id);
#else
    index_odin_->insert(v, id);
#endif
  }

 private:
  Args args_;
#ifdef P0_DGAI
  pipeann::Parameters params_;
  pipeann::DistanceL2 dist_;
  std::unique_ptr<pipeann::DynamicSSDIndex<float, uint32_t>> index_dgai_;
#else
  pipeann::IndexBuildParameters params_odin_;
  std::unique_ptr<DynamicIndex<float>> index_odin_;
#endif
};

double recall_at_10(const Truth &truth, uint64_t qid, const uint32_t *got, uint32_t visible_npts) {
  const uint32_t *row = truth.ids.data() + (qid % truth.nq) * truth.width;
  uint32_t expected[10];
  int ne = 0;
  for (uint32_t i = 0; i < truth.width && ne < 10; ++i) {
    if (row[i] < visible_npts) expected[ne++] = row[i];
  }
  if (ne == 0) return -1;
  int hit = 0;
  for (int i = 0; i < 10; ++i) {
    for (int j = 0; j < ne; ++j) {
      if (got[i] == expected[j]) {
        ++hit;
        break;
      }
    }
  }
  return static_cast<double>(hit) / ne;
}

void schedule(Queue<Task> &queue, double rate, int seconds, bool measure, uint64_t &seq) {
  if (rate <= 0 || seconds <= 0) return;
  auto phase_start = Clock::now();
  uint64_t wall_start = wall_us();
  uint64_t count = static_cast<uint64_t>(std::floor(rate * seconds));
  for (uint64_t i = 0; i < count; ++i) {
    auto offset = std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(i / rate));
    auto due = phase_start + offset;
    std::this_thread::sleep_until(due);
    queue.push(Task{seq++, wall_start + static_cast<uint64_t>(1e6 * i / rate), due, measure});
  }
  std::this_thread::sleep_until(phase_start + std::chrono::seconds(seconds));
}

int main_impl(const Args &a) {
  if (a.index.empty() || a.data.empty() || a.query.empty() || a.truth.empty() || a.output.empty()) return 2;
  uint32_t data_n = 0, data_d = 0, query_n = 0, query_d = 0;
  auto data = load_bin<float>(a.data, data_n, data_d);
  auto queries = load_bin<float>(a.query, query_n, query_d);
  auto truth = load_truth(a.truth);
  if (data_d != query_d || data_n <= a.base_npts || truth.nq != query_n) return 3;

  std::filesystem::create_directories(a.output);
  Adapter index(a, data_d);
  Queue<Task> qq, uq;
  std::atomic<uint32_t> completed_updates{0};
  std::atomic<int> query_active{0}, update_active{0};
  std::vector<Row> rows;
  std::mutex rows_mu;

  auto save_row = [&](Row row, bool measure) {
    if (!measure) return;
    std::lock_guard<std::mutex> lock(rows_mu);
    rows.push_back(std::move(row));
  };

  std::vector<std::thread> qworkers;
  for (int tid = 0; tid < a.query_threads; ++tid) {
    qworkers.emplace_back([&, tid] {
      pin_to_cpu(tid % 18);
      Task task;
      std::vector<uint32_t> ids(10);
      std::vector<float> dists(10);
      while (qq.pop(task)) {
        query_active.fetch_add(1);
        Row row;
        row.op = "query"; row.seq = task.seq; row.tid = tid; row.arrival_us = task.due_wall_us;
        auto start = Clock::now(); row.start_us = wall_us();
        pipeann::QueryStats stats;
        try {
          index.search(queries.data() + (task.seq % query_n) * query_d, ids.data(), dists.data(), stats);
        } catch (...) { row.status = "exception"; }
        auto end = Clock::now(); row.end_us = wall_us();
        row.queue_us = std::chrono::duration<double, std::micro>(start - task.due).count();
        row.service_us = std::chrono::duration<double, std::micro>(end - start).count();
        row.total_us = std::chrono::duration<double, std::micro>(end - task.due).count();
        row.visible_npts = a.base_npts + completed_updates.load();
        row.recall = recall_at_10(truth, task.seq, ids.data(), row.visible_npts);
        row.n_ios = stats.n_ios; row.io_us = stats.io_us;
        save_row(std::move(row), task.measure);
        query_active.fetch_sub(1);
      }
    });
  }

  std::vector<std::thread> uworkers;
  for (int tid = 0; tid < a.update_threads; ++tid) {
    uworkers.emplace_back([&, tid] {
      pin_to_cpu(20 + tid);
      Task task;
      while (uq.pop(task)) {
        update_active.fetch_add(1);
        Row row;
        row.op = "update"; row.seq = task.seq; row.tid = tid; row.arrival_us = task.due_wall_us;
        auto start = Clock::now(); row.start_us = wall_us();
        uint32_t id = a.base_npts + static_cast<uint32_t>(task.seq);
        try {
          index.insert(data.data() + static_cast<size_t>(id) * data_d, id);
          completed_updates.fetch_add(1);
        } catch (...) { row.status = "exception"; }
        auto end = Clock::now(); row.end_us = wall_us();
        row.queue_us = std::chrono::duration<double, std::micro>(start - task.due).count();
        row.service_us = std::chrono::duration<double, std::micro>(end - start).count();
        row.total_us = std::chrono::duration<double, std::micro>(end - task.due).count();
        row.visible_npts = a.base_npts + completed_updates.load();
        save_row(std::move(row), task.measure);
        update_active.fetch_sub(1);
      }
    });
  }

  uint64_t qseq = 0, useq = 0;
  schedule(qq, a.query_qps, a.warmup_sec, false, qseq);
  while (qq.size() || query_active.load()) std::this_thread::sleep_for(std::chrono::milliseconds(1));

  uint64_t measure_start_us = wall_us();
  std::thread up([&] { pin_to_cpu(26); schedule(uq, a.update_qps, a.duration_sec, true, useq); });
  pin_to_cpu(27);
  schedule(qq, a.query_qps, a.duration_sec, true, qseq);
  up.join();
  while (qq.size() || uq.size() || query_active.load() || update_active.load())
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  uint64_t measure_end_us = wall_us();
  qq.close(); uq.close();
  for (auto &t : qworkers) t.join();
  for (auto &t : uworkers) t.join();

  std::ofstream out(std::filesystem::path(a.output) / "ops.csv");
  out << "run_id,system,query_qps,update_qps,op,seq,thread_id,arrival_us,start_us,end_us,queue_us,service_us,total_us,recall,n_ios,io_us,visible_npts,status\n";
  for (const auto &r : rows) {
    out << a.run_id << ','
#ifdef P0_DGAI
        << "DGAI"
#else
        << "OdinANN"
#endif
        << ',' << a.query_qps << ',' << a.update_qps << ',' << r.op << ',' << r.seq << ',' << r.tid << ','
        << r.arrival_us << ',' << r.start_us << ',' << r.end_us << ',' << r.queue_us << ',' << r.service_us << ','
        << r.total_us << ',' << r.recall << ',' << r.n_ios << ',' << r.io_us << ',' << r.visible_npts << ','
        << r.status << '\n';
  }
  std::ofstream meta(std::filesystem::path(a.output) / "meta.txt");
  meta << "run_id=" << a.run_id << "\nmeasure_start_us=" << measure_start_us << "\nmeasure_end_us=" << measure_end_us
       << "\nquery_qps=" << a.query_qps << "\nupdate_qps=" << a.update_qps << "\nquery_threads=" << a.query_threads
       << "\nupdate_threads=" << a.update_threads << "\nrows=" << rows.size() << "\ncompleted_updates="
       << completed_updates.load() << "\n";
  std::cerr << "P0_DONE rows=" << rows.size() << " updates=" << completed_updates.load()
            << " measure_wall_s=" << (measure_end_us - measure_start_us) / 1e6 << "\n";
  return 0;
}

}  // namespace

int main(int argc, char **argv) {
  std::signal(SIGSEGV, crash_trace);
  std::signal(SIGABRT, crash_trace);
  try { return main_impl(parse_args(argc, argv)); }
  catch (const std::exception &e) { std::cerr << "fatal: " << e.what() << "\n"; return 1; }
}
