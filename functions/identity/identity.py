import json, os, socket, sys, uuid
import requests

HOST_JSON_PATH = "/etc/gustavo-worker/host.json"
CREDENTIAL_JSON_PATH = "/etc/gustavo-worker/credential.json"


def _get_host_ip():
    # connect-trick: no packets actually sent, just asks the OS which
    # local interface/address it would route through - relies on this
    # worker running with host networking to return a real host IP
    # rather than a container-internal bridge address.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def bootstrap_identity(device_group, nebula_username, nebula_password,
                       reporter_host=None, reporter_port=None, reporter_protocol="http",
                       registry_username=None, registry_password=None, registry_host=None):
    # one-time worker identity bootstrap - writes host.json/credential.json to disk
    # and registers with reporter's worker directory. Only runs the node_id-generating
    # part once per worker: if host.json already exists, its node_id is reused as-is
    # and never regenerated - everything else (ips, device_group) is written fresh
    # every call. Periodic refresh after this initial call is handled by a separate,
    # dedicated cron job component, not by this worker process.
    #
    # registry_host is also what pull_image compares against the registry
    # resolved from each image reference, to decide whether the stored
    # registry_username/password actually applies to that pull - see
    # read_registry_host and docker_engine.py's pull_image.
    os.makedirs(os.path.dirname(HOST_JSON_PATH), exist_ok=True)

    if os.path.exists(HOST_JSON_PATH):
        try:
            with open(HOST_JSON_PATH) as f:
                node_id = json.load(f)["node_id"]
        except Exception as e:
            print(e, file=sys.stderr)
            print("failed reading existing host.json node_id - generating a new one")
            node_id = str(uuid.uuid4())
    else:
        node_id = str(uuid.uuid4())

    host_ip = _get_host_ip()
    auth = (nebula_username, nebula_password)

    remote_ip = ""
    if reporter_host is not None:
        try:
            resp = requests.get(f"{reporter_protocol}://{reporter_host}:{reporter_port}/whoami",
                                auth=auth, timeout=10)
            if resp.status_code == 200:
                remote_ip = resp.json().get("remote_ip", "")
            else:
                print(f"whoami call failed: HTTP {resp.status_code} {resp.text}", file=sys.stderr)
        except Exception as e:
            print(e, file=sys.stderr)
            print("whoami call failed - continuing with empty remote_ip")

    try:
        with open(HOST_JSON_PATH, "w") as f:
            json.dump({"node_id": node_id, "host_ip": host_ip, "remote_ip": remote_ip,
                      "device_group": device_group}, f)
    except Exception as e:
        print(e, file=sys.stderr)
        print("failed writing host.json")

    try:
        with open(CREDENTIAL_JSON_PATH, "w") as f:
            json.dump({"username": nebula_username, "password": nebula_password,
                      "registry_username": registry_username, "registry_password": registry_password,
                      "registry_host": registry_host}, f)
        os.chmod(CREDENTIAL_JSON_PATH, 0o600)
    except Exception as e:
        print(e, file=sys.stderr)
        print("failed writing credential.json")

    if reporter_host is not None:
        try:
            resp = requests.post(f"{reporter_protocol}://{reporter_host}:{reporter_port}/api/directory/{device_group}",
                                json={"node_id": node_id, "host_ip": host_ip, "remote_ip": remote_ip},
                                auth=auth, timeout=10)
            if resp.status_code != 200:
                print(f"directory registration failed: HTTP {resp.status_code} {resp.text}", file=sys.stderr)
        except Exception as e:
            print(e, file=sys.stderr)
            print("directory registration failed")

    return node_id


def read_credential(default_username, default_password):
    # re-read on every call so a credential rotation (done by a separate,
    # dedicated credential-refresher cron job - not this process) takes
    # effect without restarting the worker. Falls back to the given
    # defaults if the file is missing, unreadable, or caught mid-write by
    # a concurrent refresh - never raises, never blocks the check-in loop.
    # `or default` rather than dict.get's own default: a bad refresh that
    # writes syntactically valid JSON with empty values ({"username": "",
    # "password": ""}) must fall back too, not adopt an empty credential -
    # dict.get only falls back when the key is missing entirely.
    try:
        with open(CREDENTIAL_JSON_PATH) as f:
            data = json.load(f)
        username = data.get("username") or default_username
        password = data.get("password") or default_password
        return username, password
    except Exception as e:
        print(e, file=sys.stderr)
        print("failed reading credential.json - using last known credential")
        return default_username, default_password


def read_registry_credential(default_username, default_password):
    # same shape and fallback rules as read_credential, for the separate
    # registry_username/registry_password fields - deliberately not the
    # same keys, since a bad refresh touching one credential shouldn't be
    # able to collide with or blank out the other.
    try:
        with open(CREDENTIAL_JSON_PATH) as f:
            data = json.load(f)
        username = data.get("registry_username") or default_username
        password = data.get("registry_password") or default_password
        return username, password
    except Exception as e:
        print(e, file=sys.stderr)
        print("failed reading credential.json for registry auth - using last known credential")
        return default_username, default_password


def read_registry_host(default_host):
    # same fallback rules as read_credential/read_registry_credential.
    # Read fresh alongside the registry credential, since a refresh that
    # rotates to a different registry entirely needs its host picked up
    # the same way the credential itself is.
    try:
        with open(CREDENTIAL_JSON_PATH) as f:
            data = json.load(f)
        return data.get("registry_host") or default_host
    except Exception as e:
        print(e, file=sys.stderr)
        print("failed reading credential.json for registry host - using last known host")
        return default_host
