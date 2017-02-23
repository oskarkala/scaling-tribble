# Delfi data collector (Espionage program) with MySQL  
  
This program fetches data from "delfi.ee" and its RSS feed.  
  
It creates a MySQL database named "delfi_db" with four tables: **pm_topnews**, **delfi_rss**, **delfi_topnews** and **delfi_mostreadnews**.  
**delfi_rss** table is filled with new entries from delfi's RSS feed: their publishing date, rss channel (category), article headline and URL. Table is updated every 1800 seconds (30 minutes).  
**delfi_topnews** table takes data from the "delfi.ee" HTML page. The top news (first 8-10 articles on top of the page) are inserted to the table in their respective order. The table is updated every 900 seconds (15 minutes).  
**delfi_mostreadnews** table also takes data from the HTML page. There is a section there with 8 currently most popular (most read) articles. Format is the same as **delfi_topnews**.  
**pm_topnews** for Postimees topnews data
  
This API has four endpoints: /pm_topnews, /delfi_rss, /delfi_topnews and /delfi_mostreadnews, which returns a JSON dump of the current state of the respective MySQL table.  
  
**Environment variables:**  
'APP_PORT': 80 is default.  
'APP_URL_PREFIX'  
  
'SQL_HOST'  
'SQL_USER'  
'SQL_PW'  
'SQL_DB'  
  
Usage:  
1. docker run --name some-mysql -e MYSQL_ROOT_PASSWORD=my-secret-pw -d mysql:tag (starts a mysql server instance)    
2. docker run --name some-app --link some-mysql:mysql_host -d -e SQL_HOST=mysql_host application-that-uses-mysql  

