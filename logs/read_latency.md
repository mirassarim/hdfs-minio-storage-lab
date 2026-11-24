## Read latency: HDFS vs S3 / MinIO

10 timed reads per row after one warm-up read.

| Payload | System | Median (ms) | p95 (ms) |
|---|---|---|---|
| 1 MB | S3 / MinIO GET | 13.5 | 76.0 |
| 1 MB | HDFS cat (incl. client start-up) | 2061.8 | 2218.8 |
| 1 MB | HDFS stat (start-up only, no data) | 1875.1 | 2096.1 |
| 100 MB | S3 / MinIO GET | 147.5 | 168.8 |
| 100 MB | HDFS cat (incl. client start-up) | 3930.3 | 4224.8 |
| 100 MB | HDFS stat (start-up only, no data) | 1892.7 | 1945.1 |

* 1 MB: HDFS net read time (cat - stat) = 186.7 ms; S3 GET = 13.5 ms.
* 100 MB: HDFS net read time (cat - stat) = 2037.7 ms; S3 GET = 147.5 ms.

Note: the HDFS rows include starting a Java client through `docker exec`, so they are not a like-for-like protocol comparison with an in-process boto3 call; the `stat` row shows that fixed cost. Everything runs on localhost.

Environment: Windows 10, Python 3.10.9, 12 logical CPUs; HDFS: 1 NameNode + 2 DataNodes (replication 2); MinIO: one server.
