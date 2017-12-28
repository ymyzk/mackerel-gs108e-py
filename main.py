import json
import os
import time

from bs4 import BeautifulSoup
import requests


API_ENDPOINT = os.environ.get("API_ENDPOINT", "https://api.mackerelio.com")
API_KEY = os.environ.get("API_KEY")
DEBUG = bool(os.environ.get("DEBUG"))
HOST_ID = os.environ.get("HOST_ID")
URL = os.environ.get("URL")
PASSWORD = os.environ.get("PASSWORD")
POLLING_TIME = int(os.environ.get("POLLING_TIME", "60"))


class Login():
    def __init__(self, endpoint, password):
        self.endpoint = endpoint
        self.password = password

    def __enter__(self):
        payload = {
            "password": self.password
        }
        response = requests.post(self.endpoint + "/login.cgi", data=payload)
        cookie = response.headers["Set-Cookie"]

        session = requests.Session()
        session.headers.update({"Cookie": cookie})
        self.session = session

        return session

    def __exit__(self, type, value, traceback):
        response = self.session.get(self.endpoint + "/logout.cgi")


def get_status():
    with Login(URL, PASSWORD) as session:
        response = session.get(URL + "/port_statistics.htm")
        now = int(time.time())
        soup = BeautifulSoup(response.text, "lxml")
        rows = soup.find_all("tr", class_="portID")
        results = [
            [int(row.find("td").get_text())] +
            [int(cell["value"], 16) for cell in row.find_all("input")]
            for row in rows
        ]

        status = {}
        for port, received, sent, error in results:
            status[port] = {
                "received": received,  # bytes/sec
                "sent": sent,  # bytes/sec
                "error": error  # packets/sec
            }

        return now, status


def calc_diff(prev, curr):
    prev_time, prev = prev
    curr_time, curr = curr

    if prev is None:
        return None

    diff = {}
    diff_time = curr_time - prev_time

    if diff_time == 0:
        return None

    for port, result in curr.items():
        diff[port] = {}
        for key, value in result.items():
            diff[port][key] = (value - prev[port][key]) / diff_time

    return diff


def convert_to_metrics(now, diff):
    metrics = []
    for port, result in diff.items():
        for key, value in result.items():
            metrics.append({
                "hostId": HOST_ID,
                "name": "custom.gs108e.port{}.{}".format(port, key),
                "time": now,
                "value": value
            })
    return metrics


def main():
    # try catch
    prev = (None, None)
    while True:
        try:
            curr = get_status()
            now = curr[0]
            diff = calc_diff(prev, curr)
            prev = curr

            if diff is None:
                time.sleep(1)
                continue

            metrics = convert_to_metrics(now, diff)
            if DEBUG: print(metrics)

            response = requests.post(
                API_ENDPOINT + "/api/v0/tsdb",
                json=metrics,
                headers={
                    "X-Api-Key": API_KEY
                })
        except Exception as e:
            print("Error:", e)

        time.sleep(POLLING_TIME)

if __name__ == "__main__":
    main()
