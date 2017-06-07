import requests
from bs4 import BeautifulSoup
from datetime import date

month_to_num = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06", "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"}

res = requests.get("https://www.timeanddate.com/holidays/us/#!hol=9565055")
c = res.content
data = BeautifulSoup(c, "html.parser")
table = data.find("table", "zebra fw tb-cl tb-hover")
tbody = table.find("tbody")
rows = tbody.find_all("tr")

tdata = []
for r in rows:
    cols = r.find_all("td")
    cols = [ele.text.strip() for ele in cols]
    row = [r.find("th").text.strip()]
    for ele in cols:
        if ele:
            row.append(ele)
    tdata.append(row)

for n, r in enumerate(tdata):
    t_stamp = r[0].split(" ")
    d_string = str(date.today().year) + "-" + month_to_num[t_stamp[0]] + "-" + t_stamp[1].zfill(2)
    tdata[n] = [d_string, r[2], ":000,000,000", "0"]

with open("holidays.txt", "w", encoding='UTF-8') as text_file:
    for row in tdata:
        print(*row, sep="|", file=text_file)