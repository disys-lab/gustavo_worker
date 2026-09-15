import sys, requests


class ReporterConnection:

    def __init__(self, reporter_host, reporter_port, nebula_username, nebula_password, protocol="http"):
        self.url_base = f"{protocol}://{reporter_host}:{reporter_port}/api/reports"
        self.auth = (nebula_username, nebula_password)

    def push_report(self, report):
        try:
            body = {
                "node_id": report["hostname"],
                "report_creation_time": report["report_creation_time"],
                "memory_usage": report["memory_usage"],
                "root_disk_usage": report["root_disk_usage"],
                "cpu_usage": report["cpu_usage"],
                "apps_containers": report["apps_containers"],
            }
            resp = requests.post(f"{self.url_base}/{report['device_group']}", json=body, auth=self.auth, timeout=10)
            if resp.status_code != 200:
                print(f"Report delivery to reporter failed: HTTP {resp.status_code} {resp.text}", file=sys.stderr)
        except Exception as e:
            print(e, file=sys.stderr)
            print("Report delivery to reporter failed")
