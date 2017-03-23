import json
import threading
import requests
import feedparser
import datetime
import os
import MySQLdb as mdb
from flask import Flask, abort, Blueprint
from flask_cors import CORS
from datetime import datetime as dt
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

rss_timer = 890
topnews_timer = 900
rus_topnews_timer = 900

pm_editorschoice_url = 'http://services.postimees.ee/rest/v1/sections/81/editorsChoice/articles'
pm_rss_url = 'http://feeds2.feedburner.com/postimees.ee/rss'

delfi_rss_url = 'http://feeds2.feedburner.com/'
delfi_rss_map = {
    'delfi_kõik': delfi_rss_url + 'delfiuudised',
    'delfi_eesti': delfi_rss_url + 'delfieesti',
    'delfi_maailm': delfi_rss_url + 'delfimaailm',
    'delfi_majandus': delfi_rss_url + 'delfimajandus',
    'delfi_sport': delfi_rss_url + 'delfisport',
    'forte_uudised': delfi_rss_url + 'forteuudised',
    'publik_uudised': delfi_rss_url + 'publikuudised',
    'rusdelfinews': delfi_rss_url + 'rusdelfinews',
    'rusdelfipolitics': delfi_rss_url + 'rusdelfipolitics',
    'rusdelfisport': delfi_rss_url + 'rusdelfisport',
    'rusdelficulturelife': delfi_rss_url + 'rusdelficulturelife',
    'rusdelfiabroad': delfi_rss_url + 'rusdelfiabroad',
    'rusdelfieconomy': delfi_rss_url + 'rusdelfieconomy',
    'rusdelfidaily': delfi_rss_url + 'rusdelfidaily'

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


def query_pm_rss_table():
    cnx = connect_to_sql()
    cursor = cnx.cursor()

    select_string = "SELECT (1) FROM pm_rss"
    cursor.execute(select_string)
    rows = cursor.fetchone()

    if rows is None:
        return False
    elif 1 in rows:
        return True


# checks the rss table for before inserting new data
def check_for_dupes(article_url):
    cnx = connect_to_sql()
    cursor = cnx.cursor()

    select_string = "SELECT (1) FROM delfi_rss WHERE article_url = %(article_url)s"

    cursor.execute(select_string, {'article_url': article_url})

    rows = cursor.fetchone()
    if rows is None:
        return False
    elif 1 in rows:
        return True


# checks the rss table for before inserting new data
def check_for_pm_dupes(article_url):
    cnx = connect_to_sql()
    cursor = cnx.cursor()

    select_string = "SELECT (1) FROM pm_rss WHERE article_url = %(article_url)s"

    cursor.execute(select_string, {'article_url': article_url})

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
def parse_date(date, ekspress=None):
    if ekspress is None:
        date_data = date.split(sep=',')
        date_data = date_data[1].split(sep=' ')

        day = day_handling(date_data[1])
        month = month_handling(date_data[2])
        year = int(date_data[3])

        timestamp = date_data[4]

        hour = int((timestamp.split(sep=":"))[0])
        minute = int((timestamp.split(sep=":"))[1])
        second = int((timestamp.split(sep=":"))[2])

    elif ekspress is True:
        date_data = date.split(sep=' ')

        year = int(date_data[0].split(sep='-')[0])
        month = int(date_data[0].split(sep='-')[1])
        day = int(date_data[0].split(sep='-')[2])
        hour = int(date_data[1].split(sep=':')[0])
        minute = int(date_data[1].split(sep=':')[1])
        second = int(date_data[1].split(sep=':')[2])

    format_date = dt(year=year, day=day, month=month, hour=hour, minute=minute, second=second)
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
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8 DEFAULT COLLATE utf8_unicode_ci")

    TABLES['delfi_editorschoice'] = (
        "CREATE TABLE IF NOT EXISTS `delfi_editorschoice` ("
        "  `article_no` int(11) NOT NULL AUTO_INCREMENT,"
        "  `article_rank` int(11) NOT NULL,"
        "  `publish_date` varchar(255) NOT NULL,"
        "  `article_category` varchar(255) NOT NULL,"
        "  `article_title` varchar(255) NOT NULL,"
        "  `article_url` varchar(255) NOT NULL,"
        "  `creation_date` varchar(255) NOT NULL,"
        "  PRIMARY KEY (`article_no`)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8 DEFAULT COLLATE utf8_unicode_ci")

    TABLES['delfi_popular'] = (
        "CREATE TABLE IF NOT EXISTS `delfi_popular` ("
        "  `article_no` int(11) NOT NULL AUTO_INCREMENT,"
        "  `article_rank` int(11) NOT NULL,"
        "  `publish_date` varchar(255) NOT NULL,"
        "  `article_category` varchar(255) NOT NULL,"
        "  `article_title` varchar(255) NOT NULL,"
        "  `article_url` varchar(255) NOT NULL,"
        "  `creation_date` varchar(255) NOT NULL,"
        "  PRIMARY KEY (`article_no`)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8 DEFAULT COLLATE utf8_unicode_ci")

    TABLES['delfi_rus_editorschoice'] = (
        "CREATE TABLE IF NOT EXISTS `delfi_rus_editorschoice` ("
        "  `article_no` int(11) NOT NULL AUTO_INCREMENT,"
        "  `article_rank` int(11) NOT NULL,"
        "  `publish_date` varchar(255) NOT NULL,"
        "  `article_category` varchar(255) NOT NULL,"
        "  `article_title` varchar(255) NOT NULL,"
        "  `article_url` varchar(255) NOT NULL,"
        "  `creation_date` varchar(255) NOT NULL,"
        "  PRIMARY KEY (`article_no`)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8 DEFAULT COLLATE utf8_unicode_ci")

    TABLES['delfi_rus_popular'] = (
        "CREATE TABLE IF NOT EXISTS `delfi_rus_popular` ("
        "  `article_no` int(11) NOT NULL AUTO_INCREMENT,"
        "  `article_rank` int(11) NOT NULL,"
        "  `publish_date` varchar(255) NOT NULL,"
        "  `article_category` varchar(255) NOT NULL,"
        "  `article_title` varchar(255) NOT NULL,"
        "  `article_url` varchar(255) NOT NULL,"
        "  `creation_date` varchar(255) NOT NULL,"
        "  PRIMARY KEY (`article_no`)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8 DEFAULT COLLATE utf8_unicode_ci")

    TABLES['pm_rss'] = (
        "CREATE TABLE IF NOT EXISTS `pm_rss` ("
        "  `article_no` int(11) NOT NULL AUTO_INCREMENT,"
        "  `article_date` varchar(255) NOT NULL,"
        "  `article_title` varchar(255) NOT NULL,"
        "  `article_url` varchar(255) NOT NULL,"
        "  PRIMARY KEY (`article_no`)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8 DEFAULT COLLATE utf8_unicode_ci")

    TABLES['pm_editorschoice'] = (
        "CREATE TABLE IF NOT EXISTS `pm_editorschoice` ("
        "  `article_no` int(11) NOT NULL AUTO_INCREMENT,"
        "  `article_rank` int(11) NOT NULL,"
        "  `publish_date` varchar(255) NOT NULL,"
        "  `article_category` varchar(255) NOT NULL,"
        "  `article_title` varchar(255) NOT NULL,"
        "  `article_url` varchar(255) NOT NULL,"
        "  `creation_date` varchar(255) NOT NULL,"
        "  PRIMARY KEY (`article_no`)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8 DEFAULT COLLATE utf8_unicode_ci")

    cnx = mdb.connect(host=SQL_HOST, user=SQL_USER, password=SQL_PW, use_unicode=True, charset="utf8")

    with cnx:
        cursor = cnx.cursor()
        cursor.execute(
            "CREATE DATABASE IF NOT EXISTS {} DEFAULT CHARACTER SET 'utf8mb4' COLLATE 'utf8mb4_unicode_ci'".format(DB_NAME))
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

    print("delfi_rss: ")
    print("add_article: ", add_article)
    print("data_article: ", data_article)

    cursor.execute(add_article, data_article)

    cnx.commit()

    cursor.close()
    cnx.close()


def insert_to_pm_rss(entry):
    article_date = entry[0]
    article_title = entry[1]
    article_url = entry[2]

    cnx = connect_to_sql()
    cursor = cnx.cursor()

    add_article = ("INSERT INTO pm_rss "
                   "(article_date, article_title, article_url) "
                   "VALUES (%s, %s, %s)")

    data_article = (article_date, article_title, article_url)

    print("delfi_rss: ")
    print("add_article: ", add_article)
    print("data_article: ", data_article)

    cursor.execute(add_article, data_article)

    cnx.commit()

    cursor.close()
    cnx.close()


def insert_to_delfi_editorschoice(entry):
    article_rank = entry[0]
    article_url = entry[1]
    publish_date = entry[2]
    article_category = entry[3]
    article_title = entry[4]
    creation_date = entry[5]

    cnx = connect_to_sql()
    cursor = cnx.cursor()

    add_article = ("INSERT INTO delfi_editorschoice "
                   "(article_rank, publish_date, article_category, article_title, article_url, creation_date) "
                   "VALUES (%s, %s, %s, %s, %s, %s)")

    data_article = (article_rank, publish_date, article_category, article_title, article_url, creation_date)

    print("delfi_editorschoice: ")
    print("add_article: ", add_article)
    print("data_article: ", data_article)

    cursor.execute(add_article, data_article)
    cnx.commit()

    cursor.close()
    cnx.close()


def insert_to_delfi_popular(entry):
    article_rank = entry[0]
    article_url = entry[1]
    publish_date = entry[2]
    article_category = entry[3]
    article_title = entry[4]
    creation_date = entry[5]

    cnx = connect_to_sql()
    cursor = cnx.cursor()

    add_article = ("INSERT INTO delfi_popular "
                   "(article_rank, publish_date, article_category, article_title, article_url, creation_date) "
                   "VALUES (%s, %s, %s, %s, %s, %s)")

    data_article = (article_rank, publish_date, article_category, article_title, article_url, creation_date)

    print("delfi_popular: ")
    print("add_article: ", add_article)
    print("data_article: ", data_article)

    cursor.execute(add_article, data_article)
    cnx.commit()

    cursor.close()
    cnx.close()


def insert_to_delfi_rus_editorschoice(entry):
    article_rank = entry[0]
    article_url = entry[1]
    publish_date = entry[2]
    article_category = entry[3]
    article_title = entry[4]
    creation_date = entry[5]

    cnx = connect_to_sql()
    cursor = cnx.cursor()

    add_article = ("INSERT INTO delfi_rus_editorschoice "
                   "(article_rank, publish_date, article_category, article_title, article_url, creation_date) "
                   "VALUES (%s, %s, %s, %s, %s, %s)")

    data_article = (article_rank, publish_date, article_category, article_title, article_url, creation_date)

    print("delfi_editorschoice: ")
    print("add_article: ", add_article)
    print("data_article: ", data_article)

    cursor.execute(add_article, data_article)
    cnx.commit()

    cursor.close()
    cnx.close()


def insert_to_delfi_rus_popular(entry):
    article_rank = entry[0]
    article_url = entry[1]
    publish_date = entry[2]
    article_category = entry[3]
    article_title = entry[4]
    creation_date = entry[5]

    cnx = connect_to_sql()
    cursor = cnx.cursor()

    add_article = ("INSERT INTO delfi_rus_popular "
                   "(article_rank, publish_date, article_category, article_title, article_url, creation_date) "
                   "VALUES (%s, %s, %s, %s, %s, %s)")

    data_article = (article_rank, publish_date, article_category, article_title, article_url, creation_date)

    print("delfi_popular: ")
    print("add_article: ", add_article)
    print("data_article: ", data_article)

    cursor.execute(add_article, data_article)
    cnx.commit()

    cursor.close()
    cnx.close()


def insert_to_pm_editorschoice(entry):
    article_rank = entry[0]
    article_url = entry[1]
    publish_date = entry[2]
    article_category = entry[3]
    article_title = entry[4]
    creation_date = entry[5]

    cnx = connect_to_sql()
    cursor = cnx.cursor()

    add_article = ("INSERT INTO pm_editorschoice "
                   "(article_rank, publish_date, article_category, article_title, article_url, creation_date) "
                   "VALUES (%s, %s, %s, %s, %s, %s)")

    data_article = (article_rank, publish_date, article_category, article_title, article_url, creation_date)

    print("pm_editorschoice: ")
    print("add_article: ", add_article)
    print("data_article: ", data_article)

    cursor.execute(add_article, data_article)
    cnx.commit()

    cursor.close()
    cnx.close()


# uses beautifulsoup to parse delfi.ee HTML data to get the urls of top frontpage
# and currently most read news
def topnews():
    print("start topnews()")
    useragent_header ={
        'User-Agent':  ua.random
    }

    data = requests.get("http://www.delfi.ee", useragent_header).text
    soup = BeautifulSoup(data, 'html.parser')

    editorschoice = soup.section
    editorschoice_array = []

    related_news_array = []
    popular_news_array = []

    related_news = editorschoice.find_all('h5')

    for i in related_news:
        for link in i.find_all('a'):
            if link.get('href').endswith('reg=1'):
                pass
            else:
                related_news_array.append(link.get('href'))

    for link in editorschoice.find_all('a'):
        if link.get('href').endswith('reg=1') \
                or link.get('href').endswith('.jpg') \
                or link.get('href') in related_news_array:
            pass
        else:
            editorschoice_array.append(link.get('href'))

    popular_news = soup.find(id="mostread-news")

    for link in popular_news.find_all('a'):
        if link.get('href').endswith('reg=1'):
            pass
        else:
            popular_news_array.append(link.get('href'))

    popular_news_array = popular_news_array
    editorschoice_array = remove_duplicates(editorschoice_array)

    create_top_list(popular_news_array, 'popular')
    create_top_list(editorschoice_array, 'editorschoice')

    pm_data = requests.get(pm_editorschoice_url).text
    pm_data = json.loads(pm_data)

    current_time = str(dt.now())

    for x, i in enumerate(pm_data):
        article_rank = x + 1
        publish_date = i['datePublished']
        article_title = i['editorsChoice']['headline']
        article_url = 'http://www.postimees.ee/' + str(i['id'])
        article_category = i['sectionBreadcrumb'][0]['domain']
        creation_date = current_time

        entry = [article_rank, article_url, publish_date, article_category, article_title, creation_date]
        insert_to_pm_editorschoice(entry=entry)

    threading.Timer(topnews_timer, topnews).start()


def rus_topnews():
    print("start rus_topnews()")
    useragent_header ={
        'User-Agent':  ua.random
    }

    data = requests.get("http://rus.delfi.ee", useragent_header).text
    soup = BeautifulSoup(data, 'html.parser')

    editorschoice = soup.section
    editorschoice_array = []

    related_news_array = []
    popular_news_array = []

    related_news = editorschoice.find_all('h5')

    for i in related_news:
        for link in i.find_all('a'):
            if link.get('href').endswith('reg=1'):
                pass
            else:
                related_news_array.append(link.get('href'))

    for link in editorschoice.find_all('a'):
        if link.get('href').endswith('reg=1') \
                or link.get('href').endswith('.jpg') \
                or link.get('href') in related_news_array:
            pass
        else:
            editorschoice_array.append(link.get('href'))

    popular_news = soup.find(id="mostread-news")

    for link in popular_news.find_all('a'):
        if link.get('href').endswith('reg=1'):
            pass
        else:
            popular_news_array.append(link.get('href'))

    popular_news_array = popular_news_array
    editorschoice_array = remove_duplicates(editorschoice_array)

    create_top_list(popular_news_array, 'rus_popular')
    create_top_list(editorschoice_array, 'rus_editorschoice')

    threading.Timer(rus_topnews_timer, rus_topnews).start()


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


# populates the topnews & popular tables
def create_top_list(array, table):
    current_time = str(dt.now())
    for i, item in enumerate(array):
        from_db_item = match_articles(item)
        if from_db_item == "N/A":
            entry = [i + 1, item, from_db_item, from_db_item, from_db_item, current_time]
        else:
            entry = [i + 1, item, from_db_item[1], from_db_item[2], from_db_item[3], current_time]

        if table == 'editorschoice':
            insert_to_delfi_editorschoice(entry=entry)
        elif table == 'popular':
            insert_to_delfi_popular(entry=entry)
        elif table == 'rus_editorschoice':
            insert_to_delfi_rus_editorschoice(entry=entry)
        elif table == 'rus_popular':
            insert_to_delfi_rus_popular(entry=entry)


# threaded method to insert latest rss items
def add_rss():
    print("start add_rss()")

    data = requests.get("http://ekspress.delfi.ee").text
    soup = BeautifulSoup(data, 'html.parser')

    delfi_rss_array = []
    ekspress_array = []

    for link in soup.find_all('a'):
        article_url = link.get('href')
        if check_for_dupes(article_url) is False:
            if 'ekspress.delfi' in article_url and 'linear=1' not in article_url:
                ekspress_array.append(article_url)

                article_data = requests.get(article_url).text
                article_soup = BeautifulSoup(article_data, 'html.parser')

                title = article_soup.find("meta", property="og:title")
                publish_date = article_soup.find("meta", property="article:published_time")
                publish_date = datetime.datetime.fromtimestamp(int(publish_date["content"])).strftime(
                    '%Y-%m-%d %H:%M:%S')
                date = parse_date(str(publish_date), ekspress=True)
                entry = ([date, 'ekspress', title['content'], article_url])
                delfi_rss_array.append(entry)

    for i in delfi_rss_map.keys():
        feed = feedparser.parse(delfi_rss_map[i])
        for y, item in enumerate(feed['items']):
            date = parse_date(item['published'])
            if i == 'rusdelfiabroad':
                entry = [date, i, item['title'], item['link']]
            else:
                entry = [date, i, item['title'], item['feedburner_origlink']]
            delfi_rss_array.append(entry)
    delfi_rss_array = bubble_sort(delfi_rss_array)
    for i, item in enumerate(delfi_rss_array):
        if check_for_dupes(item[3]) is False:
            insert_to_delfi_rss(item)

    threading.Timer(rss_timer, add_rss).start()


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


# threaded method to insert latest rss items
def add_pm_rss():
    print("start add_pm_rss()")
    pm_rss_array = []
    feed = feedparser.parse(pm_rss_url)
    for i, item in enumerate(feed['items']):
        date = parse_date(item['published'])
        entry = [date, item['title'], item['link']]
        pm_rss_array.append(entry)

    delfi_rss_array = bubble_sort(pm_rss_array)
    for i, item in enumerate(delfi_rss_array):
        if check_for_pm_dupes(item[2]) is False:
            insert_to_pm_rss(item)

    threading.Timer(rss_timer, add_pm_rss).start()


# run once to populate the rss table
def fill_pm_rss_table():
    if query_pm_rss_table() is None:
        pm_rss_array = []
        feed = feedparser.parse(pm_rss_url)
        for i, item in enumerate(feed['items']):
            date = parse_date(item['published'])
            entry = [date, item['title'], item['link']]
            pm_rss_array.append(entry)

        pm_rss_array = bubble_sort(pm_rss_array)
        for i, item in enumerate(pm_rss_array):
            insert_to_pm_rss(item)


@bp.route('/<slug>')
def get_rss_data(slug):
    if slug == 'delfi_rss' or slug == 'delfi_editorschoice' \
            or slug == 'delfi_popular' or slug == 'pm_editorschoice'\
            or slug == 'delfi_rus_popular' or slug == 'delfi_rus_editorschocie'\
            or slug == 'pm_rss':

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
add_pm_rss()
topnews()
rus_topnews()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(APP_PORT))
    #app.run()
