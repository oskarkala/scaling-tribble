import json
import threading
import requests
import feedparser
import os
import MySQLdb as mdb
from flask import Flask, abort, Blueprint
from flask_cors import CORS
from datetime import datetime
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

ua = UserAgent()
bp = Blueprint('delfi_007', __name__, template_folder='templates')

APP_PORT = 80
if 'APP_PORT' in os.environ:
    APP_PORT = os.environ['APP_PORT']

APP_URL_PREFIX = ''
if 'APP_URL_PREFIX' in os.environ:
    APP_URL_PREFIX = os.environ['APP_URL_PREFIX']

SQL_HOST = 'localhost'
if 'SQL_HOST' in os.environ:
    SQL_HOST = os.environ['SQL_HOST']

SQL_USER = 'root'
if 'SQL_USER' in os.environ:
    SQL_USER = os.environ['SQL_USER']

SQL_PW = 'lumi'
if 'SQL_PW' in os.environ:
    SQL_PW = os.environ['SQL_PW']

SQL_DB = 'delfi_db'
if 'SQL_DB' in os.environ:
    SQL_DB = os.environ['SQL_DB']

rss_timer = 1800
topnews_timer = 900

pm_topnews_url = 'http://services.postimees.ee/rest/v1/sections/81/editorsChoice/articles'

delfi_rss_url = 'http://feeds2.feedburner.com/'
delfi_rss_map = {
    'delfi_kõik': delfi_rss_url + 'delfiuudised',
    'delfi_eesti': delfi_rss_url + 'delfieesti',
    'delfi_maailm': delfi_rss_url + 'delfimaailm',
    'delfi_majandus': delfi_rss_url + 'delfimajandus',
    'delfi_110-112': delfi_rss_url + 'delfi110-112',
    'delfi_sport': delfi_rss_url + 'delfisport',
    'forte_uudised': delfi_rss_url + 'forteuudised',
    'publik_uudised': delfi_rss_url + 'publikuudised'
}


def dumpjson(dict):
    return json.dumps(dict, ensure_ascii=False).encode('utf-8')


def connect_to_sql():
    cnx = mdb.connect(host=SQL_HOST, user=SQL_USER, password=SQL_PW, database=SQL_DB, use_unicode=True,
                      charset="utf8")
    return cnx


def query_rss_table():
    cnx = connect_to_sql()
    cursor = cnx.cursor()

    select_string = "SELECT (1) FROM delfi_rss"
    cursor.execute(select_string)
    rows = cursor.fetchone()

    if rows is None:
        return False
    elif 1 in rows:
        return True


# checks the rss table for before inserting new data
def check_for_dupes(article_url, article_date, article_category):
    cnx = connect_to_sql()
    cursor = cnx.cursor()

    select_string = "SELECT (1) FROM delfi_rss WHERE article_url = %(article_url)s AND " \
                    "article_date = %(article_date)s AND article_category = %(article_category)s"
    cursor.execute(select_string, {'article_url': article_url,
                                   'article_date': article_date,
                                   'article_category': article_category})

    rows = cursor.fetchone()
    if rows is None:
        return False
    elif 1 in rows:
        return True


# dupes removal
def remove_duplicates(seq):
    seen = set()
    seen_add = seen.add
    return [x for x in seq if not (x in seen or seen_add(x))]


# sorting
def bubble_sort(seq):
    changed = True
    while changed:
        changed = False
        for i in range(len(seq) - 1):
            if seq[i][0] > seq[i + 1][0]:
                seq[i], seq[i + 1] = seq[i + 1], seq[i]
                changed = True
    return seq


def day_handling(day):
    day_handler = {
        '01': 1,
        '02': 2,
        '03': 3,
        '04': 4,
        '05': 5,
        '06': 6,
        '07': 7,
        '08': 8,
        '09': 9
    }
    if int(day) >= 10:
        day = int(day)
    else:
        day = day_handler[day]
    return day


def month_handling(month):
    month_handler = {
        'Jan': 1,
        'Feb': 2,
        'Mar': 3,
        'Apr': 4,
        'May': 5,
        'Jun': 6,
        'Jul': 7,
        'Aug': 8,
        'Sep': 9,
        'Oct': 10,
        'Nov': 11,
        'Dec': 12,
    }
    return month_handler[month]


# straight-forward
def parse_date(date):
    date_data = date.split(sep=',')
    date_data = date_data[1].split(sep=' ')

    day = day_handling(date_data[1])
    month = month_handling(date_data[2])
    year = int(date_data[3])

    timestamp = date_data[4]

    hour = int((timestamp.split(sep=":"))[0])
    minute = int((timestamp.split(sep=":"))[1])
    second = int((timestamp.split(sep=":"))[2])

    format_date = datetime(year=year, day=day, month=month, hour=hour, minute=minute, second=second)
    return format_date


# database creation
def init_database():
    DB_NAME = SQL_DB

    TABLES = {}
    TABLES['delfi_rss'] = (
        "CREATE TABLE IF NOT EXISTS `delfi_rss` ("
        "  `article_no` int(11) NOT NULL AUTO_INCREMENT,"
        "  `article_date` varchar(255) NOT NULL,"
        "  `article_category` varchar(255) NOT NULL,"
        "  `article_title` varchar(255) NOT NULL,"
        "  `article_url` varchar(255) NOT NULL,"
        "  PRIMARY KEY (`article_no`)"
        ") ENGINE=InnoDB")

    TABLES['delfi_topnews'] = (
        "CREATE TABLE IF NOT EXISTS `delfi_topnews` ("
        "  `article_no` int(11) NOT NULL AUTO_INCREMENT,"
        "  `article_rank` int(11) NOT NULL,"
        "  `publish_date` varchar(255) NOT NULL,"
        "  `article_category` varchar(255) NOT NULL,"
        "  `article_title` varchar(255) NOT NULL,"
        "  `article_url` varchar(255) NOT NULL,"
        "  `creation_date` varchar(255) NOT NULL,"
        "  PRIMARY KEY (`article_no`)"
        ") ENGINE=InnoDB")

    TABLES['delfi_mostreadnews'] = (
        "CREATE TABLE IF NOT EXISTS `delfi_mostreadnews` ("
        "  `article_no` int(11) NOT NULL AUTO_INCREMENT,"
        "  `article_rank` int(11) NOT NULL,"
        "  `publish_date` varchar(255) NOT NULL,"
        "  `article_category` varchar(255) NOT NULL,"
        "  `article_title` varchar(255) NOT NULL,"
        "  `article_url` varchar(255) NOT NULL,"
        "  `creation_date` varchar(255) NOT NULL,"
        "  PRIMARY KEY (`article_no`)"
        ") ENGINE=InnoDB")

    TABLES['pm_topnews'] = (
        "CREATE TABLE IF NOT EXISTS `pm_topnews` ("
        "  `article_no` int(11) NOT NULL AUTO_INCREMENT,"
        "  `article_rank` int(11) NOT NULL,"
        "  `publish_date` varchar(255) NOT NULL,"
        "  `article_category` varchar(255) NOT NULL,"
        "  `article_title` varchar(255) NOT NULL,"
        "  `article_url` varchar(255) NOT NULL,"
        "  `creation_date` varchar(255) NOT NULL,"
        "  PRIMARY KEY (`article_no`)"
        ") ENGINE=InnoDB")

    cnx = mdb.connect(host=SQL_HOST, user=SQL_USER, password=SQL_PW, use_unicode=True, charset="utf8")

    with cnx:
        cursor = cnx.cursor()
        cursor.execute(
            "CREATE DATABASE IF NOT EXISTS {} DEFAULT CHARACTER SET 'utf8'".format(DB_NAME))
        cursor.execute(
            "USE {}".format(DB_NAME)
        )
        for name, ddl in TABLES.items():
            cursor.execute(ddl)
        cnx.commit()


def insert_to_delfi_rss(entry):
    article_date = entry[0]
    article_category = entry[1]
    article_title = entry[2]
    article_url = entry[3]

    cnx = connect_to_sql()
    cursor = cnx.cursor()

    add_article = ("INSERT INTO delfi_rss "
                   "(article_date, article_category, article_title, article_url) "
                   "VALUES (%s, %s, %s, %s)")

    data_article = (article_date, article_category, article_title, article_url)

    cursor.execute(add_article, data_article)

    cnx.commit()

    cursor.close()
    cnx.close()


def insert_to_delfi_topnews(entry):
    article_rank = entry[0]
    article_url = entry[1]
    publish_date = entry[2]
    article_category = entry[3]
    article_title = entry[4]
    creation_date = entry[5]

    cnx = connect_to_sql()
    cursor = cnx.cursor()

    add_article = ("INSERT INTO delfi_topnews "
                   "(article_rank, publish_date, article_category, article_title, article_url, creation_date) "
                   "VALUES (%s, %s, %s, %s, %s, %s)")

    data_article = (article_rank, publish_date, article_category, article_title, article_url, creation_date)

    cursor.execute(add_article, data_article)
    cnx.commit()

    cursor.close()
    cnx.close()


def insert_to_delfi_mostreadnews(entry):
    article_rank = entry[0]
    article_url = entry[1]
    publish_date = entry[2]
    article_category = entry[3]
    article_title = entry[4]
    creation_date = entry[5]

    cnx = connect_to_sql()
    cursor = cnx.cursor()

    add_article = ("INSERT INTO delfi_mostreadnews "
                   "(article_rank, publish_date, article_category, article_title, article_url, creation_date) "
                   "VALUES (%s, %s, %s, %s, %s, %s)")

    data_article = (article_rank, publish_date, article_category, article_title, article_url, creation_date)

    cursor.execute(add_article, data_article)
    cnx.commit()

    cursor.close()
    cnx.close()


def insert_to_pm_topnews(entry):
    article_rank = entry[0]
    article_url = entry[1]
    publish_date = entry[2]
    article_category = entry[3]
    article_title = entry[4]
    creation_date = entry[5]

    cnx = connect_to_sql()
    cursor = cnx.cursor()

    add_article = ("INSERT INTO pm_topnews "
                   "(article_rank, publish_date, article_category, article_title, article_url, creation_date) "
                   "VALUES (%s, %s, %s, %s, %s)")

    data_article = (article_rank, publish_date, article_category, article_title, article_url, creation_date)

    cursor.execute(add_article, data_article)
    cnx.commit()

    cursor.close()
    cnx.close()

#
# def pm_topews():
#     pm_data = requests.get(pm_topnews_url).text
#     pm_data = json.loads(pm_data)
#     for x, i in enumerate(pm_data):
#         article_rank = x + 1
#         publish_date = i['datePublished']
#         article_title = i['editorsChoice']['headline']
#         article_url = 'http://www.postimees.ee/' + str(i['id'])
#         article_category = i['sectionBreadcrumb'][1]['domain']
#
#         entry = [article_rank, article_url, publish_date, article_category, article_title]
#         insert_to_delfi_topnews(entry=entry)
#         print(entry)


# uses beautifulsoup to parse delfi.ee HTML data to get the urls of top frontpage
# and currently most read news
def topnews():
    useragent_header ={
        'User-Agent':  ua.random
    }

    data = requests.get("http://www.delfi.ee", useragent_header).text
    soup = BeautifulSoup(data, 'html.parser')

    top_news = soup.section
    top_news_array = []

    related_news_array = []
    mostread_news_array = []

    related_news = top_news.find_all('h5')

    for i in related_news:
        for link in i.find_all('a'):
            if link.get('href').endswith('reg=1'):
                pass
            else:
                related_news_array.append(link.get('href'))

    for link in top_news.find_all('a'):
        if link.get('href').endswith('reg=1') \
                or link.get('href').endswith('.jpg') \
                or link.get('href') in related_news_array:
            pass
        else:
            top_news_array.append(link.get('href'))

    mostread_news = soup.find(id="mostread-news")

    for link in mostread_news.find_all('a'):
        if link.get('href').endswith('reg=1'):
            pass
        else:
            mostread_news_array.append(link.get('href'))

    mostread_news_array = mostread_news_array
    top_news_array = remove_duplicates(top_news_array)

    create_top_list(mostread_news_array, 'mostread')
    create_top_list(top_news_array, 'topnews')

    pm_data = requests.get(pm_topnews_url).text
    pm_data = json.loads(pm_data)

    current_time = str(datetime.now())

    for x, i in enumerate(pm_data):
        article_rank = x + 1
        publish_date = i['datePublished']
        article_title = i['editorsChoice']['headline']
        article_url = 'http://www.postimees.ee/' + str(i['id'])
        article_category = i['sectionBreadcrumb'][1]['domain']
        creation_date = current_time

        entry = [article_rank, article_url, publish_date, article_category, article_title, creation_date]
        insert_to_pm_topnews(entry=entry)
        #print(entry)

    threading.Timer(topnews_timer, topnews).start()


# check the rss table for data on the article URL
def match_articles(article_url):
    cnx = connect_to_sql()
    cursor = cnx.cursor()

    select_string = "SELECT * FROM delfi_rss WHERE article_url = %(article_url)s"
    cursor.execute(select_string, {'article_url': article_url})

    rows = cursor.fetchone()
    if rows is None:
        return "N/A"
    else:
        return rows


# threaded method to insert latest rss items
def add_rss():
    delfi_rss_array = []
    for i in delfi_rss_map.keys():
        feed = feedparser.parse(delfi_rss_map[i])
        for y, item in enumerate(feed['items']):
            date = parse_date(item['published'])
            entry = [date, i, item['title'], item['feedburner_origlink']]
            delfi_rss_array.append(entry)

    delfi_rss_array = bubble_sort(delfi_rss_array)
    for i, item in enumerate(delfi_rss_array):
        if check_for_dupes(item[3], item[0], item[1]) is False:
            insert_to_delfi_rss(item)

    threading.Timer(rss_timer, add_rss).start()


# populates the topnews & mostread tables
def create_top_list(array, table):
    current_time = str(datetime.now())
    for i, item in enumerate(array):
        from_db_item = match_articles(item)
        if from_db_item == "N/A":
            entry = [i + 1, item, from_db_item, from_db_item, from_db_item, current_time]
        else:
            entry = [i + 1, item, from_db_item[1], from_db_item[2], from_db_item[3], current_time]

        if table == 'topnews':
            insert_to_delfi_topnews(entry=entry)
        elif table == 'mostread':
            insert_to_delfi_mostreadnews(entry=entry)


# run once to populate the rss table
def fill_rss_table():
    if query_rss_table() is None:
        delfi_rss_array = []
        for i in delfi_rss_map.keys():
            feed = feedparser.parse(delfi_rss_map[i])
            for y, item in enumerate(feed['items']):
                date = parse_date(item['published'])
                entry = [date, i, item['title'], item['feedburner_origlink']]
                delfi_rss_array.append(entry)

        delfi_rss_array = bubble_sort(delfi_rss_array)
        for i, item in enumerate(delfi_rss_array):
            insert_to_delfi_rss(item)


@bp.route('/<slug>')
def get_rss_data(slug):
    if slug == 'delfi_rss' or slug == 'delfi_topnews' or slug == 'delfi_mostreadnews' or slug == 'pm_topnews':
        cnx = connect_to_sql()
        cursor = cnx.cursor()

        select_string = "SELECT * FROM " + slug
        cursor.execute(select_string)

        rows = cursor.fetchall()
        resp = dumpjson(rows)
    else:
        resp = abort(404)
    return resp


@bp.after_request
def add_header(response):
    response.cache_control.max_age = 0
    return response


app = Flask(__name__)
app.register_blueprint(bp, url_prefix=APP_URL_PREFIX)
CORS(app, resources=r'/*')

init_database()
fill_rss_table()
add_rss()
topnews()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(APP_PORT))
    #app.run()
