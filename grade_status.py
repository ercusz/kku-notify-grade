import requests
from bs4 import BeautifulSoup

def getStatus(acadyear: int, semester: int, course_code: str, sec: int):
    url = f'https://reg-mirror.kku.ac.th/registrar/class_info_status.asp?acadyear={acadyear}&semester={semester}&coursecode={course_code}'
    req = requests.get(url)
    soup = BeautifulSoup(req.content, 'html.parser')

    for tr in soup.find_all('tr', class_='NormalDetail'):
        course_name = tr.find_all('td')[2].get_text().lstrip(" ")
        section = int(tr.find_all('td')[4].get_text())
        status = tr.find_all("td")[8].find("img")["title"]
        if section == sec:
            return acadyear, semester, course_code, course_name, sec, status

    return None
