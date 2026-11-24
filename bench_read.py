"""Task 4: read latency, HDFS vs S3/MinIO (Lab 8-9).

The containers must be running:  docker compose up -d
    python bench_read.py             # 10 timed reads per case
    python bench_read.py --runs 20

Method
  * Two payloads of random bytes (1 MB and 100 MB) are stored in both systems:
    in MinIO as objects, in HDFS as files (written through `hdfs dfs -put`).
  * S3 read  = boto3 get_object(...).read(), timed in-process.
  * HDFS read = `docker exec hdfs_namenode hdfs dfs -cat <file>`, timed from the
    host. This launches a Java client process every time, so a fixed start-up
    cost (docker exec + JVM + NameNode lookup) is included. To make it visible
    we also time `hdfs dfs -stat`, which starts the same process but reads no
    data. "HDFS net" = median(cat) - median(stat).
  * One untimed warm-up read per case, then --runs timed reads.
  * p95 = the ceil(0.95 * n)-th smallest value (nearest-rank method).
Results are printed and saved to logs/read_latency.md.
"""
import argparse
import math
import os
import platform
import statistics
import subprocess
import tempfile
import time

import s3_client as storage

NAMENODE = "hdfs_namenode"
HDFS_DIR = "/user/student/data"
CASES = [("1 MB", 1), ("100 MB", 100)]      # label, size in MB


def p95(values):
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def put_to_hdfs(local_path, hdfs_path):
    """Write a local file into HDFS by streaming it through `hdfs dfs -put - <dst>`."""
    with open(local_path, "rb") as source:
        subprocess.run(
            ["docker", "exec", "-i", NAMENODE, "hdfs", "dfs", "-put", "-f", "-", hdfs_path],
            stdin=source, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def time_s3_get(key):
    start = time.perf_counter()
    storage.s3.get_object(Bucket=storage.BUCKET_NAME, Key=key)["Body"].read()
    return (time.perf_counter() - start) * 1000.0


def _time_hdfs(command, path):
    start = time.perf_counter()
    subprocess.run(["docker", "exec", NAMENODE, "hdfs", "dfs", *command, path],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return (time.perf_counter() - start) * 1000.0


def time_hdfs_cat(path):
    return _time_hdfs(["-cat"], path)


def time_hdfs_stat(path):
    return _time_hdfs(["-stat", "%b"], path)


def main():
    parser = argparse.ArgumentParser(description="HDFS vs S3 read latency")
    parser.add_argument("--runs", type=int, default=10, help="timed reads per case")
    args = parser.parse_args()

    storage.init_storage()
    lines = ["## Read latency: HDFS vs S3 / MinIO\n",
             f"{args.runs} timed reads per row after one warm-up read.\n",
             "| Payload | System | Median (ms) | p95 (ms) |",
             "|---|---|---|---|"]
    net_notes = []

    with tempfile.TemporaryDirectory() as tmp:
        for label, megabytes in CASES:
            local = os.path.join(tmp, f"bench_{megabytes}m.bin")
            with open(local, "wb") as f:
                f.write(os.urandom(megabytes * 1024 * 1024))
            key = f"bench/bench_{megabytes}m.bin"
            hdfs_path = f"{HDFS_DIR}/bench_{megabytes}m.bin"

            print(f"-> {label}: storing the payload in MinIO and HDFS ...", flush=True)
            storage.upload_object(key, local, {"purpose": "latency-benchmark"})
            put_to_hdfs(local, hdfs_path)

            medians = {}
            for system, function, target in [
                    ("S3 / MinIO GET", time_s3_get, key),
                    ("HDFS cat (incl. client start-up)", time_hdfs_cat, hdfs_path),
                    ("HDFS stat (start-up only, no data)", time_hdfs_stat, hdfs_path)]:
                print(f"   {system} ...", flush=True)
                function(target)                                  # warm-up
                values = [function(target) for _ in range(args.runs)]
                medians[system] = statistics.median(values)
                lines.append(f"| {label} | {system} | {medians[system]:.1f} "
                             f"| {p95(values):.1f} |")

            net = (medians["HDFS cat (incl. client start-up)"]
                   - medians["HDFS stat (start-up only, no data)"])
            net_notes.append(f"* {label}: HDFS net read time (cat - stat) = {net:.1f} ms; "
                             f"S3 GET = {medians['S3 / MinIO GET']:.1f} ms.")

    lines.append("\n" + "\n".join(net_notes))
    lines.append(
        "\nNote: the HDFS rows include starting a Java client through `docker exec`, "
        "so they are not a like-for-like protocol comparison with an in-process "
        "boto3 call; the `stat` row shows that fixed cost. Everything runs on "
        "localhost.")
    lines.append(
        f"\nEnvironment: {platform.system()} {platform.release()}, "
        f"Python {platform.python_version()}, {os.cpu_count()} logical CPUs; "
        "HDFS: 1 NameNode + 2 DataNodes (replication 2); MinIO: one server.")

    report = "\n".join(lines)
    print("\n" + report)
    os.makedirs("logs", exist_ok=True)
    with open(os.path.join("logs", "read_latency.md"), "w", encoding="utf-8") as f:
        f.write(report + "\n")
    print("\nSaved to logs/read_latency.md")


if __name__ == "__main__":
    main()
