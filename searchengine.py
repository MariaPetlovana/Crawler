__author__ = 'Masha'

import urllib
import sqlite3
import re
from bs4 import *
from urllib.parse import urljoin

# Создать список игнорируемых слов
ignorewords=set(['the','of','to','and','a','in','is','it'])

class crawler:
    # Инициализировать паука, передав ему имя базы данных
    def __init__(self,dbname):
        self.con=sqlite3.connect(dbname)

    def __del__(self):
        self.con.close( )

    def dbcommit(self):
        self.con.commit( )

    def createindextables(self):
        self.con.execute('create table if not exists urllist(url)')
        self.con.execute('create table if not exists wordlist(word)')
        self.con.execute('create table if not exists wordlocation(urlid,wordid,location)')
        self.con.execute('create table if not exists link(fromid integer,toid integer)')
        self.con.execute('create table if not exists linkwords(wordid,linkid)')
        self.con.execute('create index if not exists wordidx on wordlist(word)')
        self.con.execute('create index if not exists urlidx on urllist(url)')
        self.con.execute('create index if not exists wordurlidx on wordlocation(wordid)')
        self.con.execute('create index if not exists urltoidx on link(toid)')
        self.con.execute('create index if not exists urlfromidx on link(fromid)')
        self.dbcommit( )

    # Вспомогательная функция для получения идентификатора и
    # добавления записи, если такой еще нет
    def getentryid(self,table,field,value,createnew=True):
        cur=self.con.execute(
        "select rowid from %s where %s='%s'" % (table,field,value))
        res=cur.fetchone( )
        if res==None:
            cur=self.con.execute(
            "insert into %s (%s) values ('%s')" % (table,field,value))
            return cur.lastrowid
        else:
            return res[0]

    # Индексирование одной страницы
    def addtoindex(self,url,soup):
        if self.isindexed(url): return
        print('Индексируется '+url)

        # Получить список слов
        text=self.gettextonly(soup)
        words=self.separatewords(text)

        # Получить идентификатор URL
        urlid=self.getentryid('urllist','url',url)

        # Связать каждое слово с этим URL
        for i in range(len(words)):
            word=words[i]
            if word in ignorewords: continue
            wordid=self.getentryid('wordlist','word',word)
            self.con.execute("insert into wordlocation(urlid,wordid,location) \
                values (%d,%d,%d)" % (urlid,wordid,i))

    # Извлечение текста из HTML-страницы (без тегов)
    def gettextonly(self,soup):
        v=soup.string
        if v==None:
            c=soup.contents
            resulttext=''
            for t in c:
                subtext=self.gettextonly(t)
                resulttext+=subtext+'\n'
            return resulttext
        else:
            return v.strip( )

    # Разбиение текста на слова
    def separatewords(self,text):
        splitter=re.compile('\\W*')
        return [s.lower( ) for s in splitter.split(text) if s!='']

    # Возвращает true, если данный URL уже проиндексирован
    def isindexed(self,url):
        u=self.con.execute \
            ("select rowid from urllist where url='%s'" % url).fetchone( )
        if u!=None:
            # Проверяем, что страница посещалась
            v=self.con.execute(
            'select * from wordlocation where urlid=%d' % u[0]).fetchone( )
            if v!=None: return True
        return False

    # Добавление ссылки с одной страницы на другую
    def addlinkref(self,urlFrom,urlTo,linkText):
        pass

    # Начиная с заданного списка страниц, выполняет поиск в ширину
    # до заданной глубины, индексируя все встречающиеся по пути
    # страницы
    def crawl(self,pages,depth=2):
        for i in range(depth):
            newpages=set( )
            for page in pages:
                try:
                    c=urllib.request.urlopen(page)
                except:
                    print("Не могу открыть %s" % page)
                    continue
                soup=BeautifulSoup(c.read( ))
                self.addtoindex(page,soup)

                links=soup('a')
                for link in links:
                    if ('href' in dict(link.attrs)):
                        url=urljoin(page,link['href'])
                        if url.find("'")!=-1: continue
                        url=url.split('#')[0] # удалить часть URL после знака #
                        if url[0:4]=='http' and not self.isindexed(url):
                            newpages.add(url)
                        linkText=self.gettextonly(link)
                        self.addlinkref(page,url,linkText)

                self.dbcommit( )

        pages=newpages

    def calculatepagerank(self,iterations=20):
        # стираем текущее содержимое таблицы PageRank
        self.con.execute('drop table if exists pagerank')
        self.con.execute('create table pagerank(urlid primary key,score)')

        # в начальный момент ранг для каждого URL равен 1
        self.con.execute('insert into pagerank select rowid, 1.0 from urllist')
        self.dbcommit( )

        for i in range(iterations):
            print("Итерация %d" % (i))
            for (urlid,) in self.con.execute('select rowid from urllist'):
                pr=0.15

            # В цикле обходим все страницы, ссылающиеся на данную
            for (linker,) in self.con.execute(
            'select distinct fromid from link where toid=%d' % urlid):
                # Находим ранг ссылающейся страницы
                linkingpr=self.con.execute(
                'select score from pagerank where urlid=%d' % linker).fetchone( )[0]

                # Находим общее число ссылок на ссылающейся странице
                linkingcount=self.con.execute(
                'select count(*) from link where fromid=%d' % linker).fetchone( )[0]
                pr+=0.85*(linkingpr/linkingcount)
            self.con.execute(
            'update pagerank set score=%f where urlid=%d' % (pr,urlid))
        self.dbcommit( )

class searcher:
    def __init__(self,dbname):
        self.con=sqlite3.connect(dbname)

    def __del__(self):
        self.con.close( )

    def getmatchrows(self,q):
        # Строки для построения запроса
        fieldlist='w0.urlid'
        tablelist=''
        clauselist=''
        wordids=[]

        # Разбить поисковый запрос на слова по пробелам
        words=q.split(' ')
        tablenumber=0

        for word in words:
            # Получить идентификатор слова
            wordrow=self.con.execute(
                "select rowid from wordlist where word='%s'" % word).fetchone( )
            if wordrow!=None:
                wordid=wordrow[0]
                wordids.append(wordid)
                if tablenumber>0:
                    tablelist+=','
                    clauselist+=' and '
                    clauselist+='w%d.urlid=w%d.urlid and ' % (tablenumber-1,tablenumber)
                fieldlist+=',w%d.location' % tablenumber
                tablelist+='wordlocation w%d' % tablenumber
                clauselist+='w%d.wordid=%d' % (tablenumber,wordid)
                tablenumber+=1

        # Создание запроса из отдельных частей
        fullquery='select %s from %s where %s' % (fieldlist,tablelist,clauselist)
        cur=self.con.execute(fullquery)
        rows=[row for row in cur]

        return rows,wordids

    def getscoredlist(self,rows,wordids):
        totalscores=dict([(row[0],0) for row in rows])

        # Сюда мы позже поместим функции ранжирования
        weights=[(1.0,self.locationscore(rows)),
                 (1.0,self.frequencyscore(rows)),
                 (1.0,self.pagerankscore(rows))]

        for (weight,scores) in weights:
            for url in totalscores:
                totalscores[url]+=weight*scores[url]

        return totalscores

    def geturlname(self,id):
        return self.con.execute(
        "select url from urllist where rowid=%d" % id).fetchone( )[0]

    def query(self,q):
        rows,wordids=self.getmatchrows(q)
        scores=self.getscoredlist(rows,wordids)
        rankedscores=sorted([(score,url) for (url,score) in scores.items( )],\
        reverse=1)
        for (score,urlid) in rankedscores[0:10]:
            print('%f\t%s' % (score,self.geturlname(urlid)))

    def normalizescores(self,scores,smallIsBetter=0):
        vsmall=0.00001 # Предотвратить деление на нуль
        if smallIsBetter:
            minscore=min(scores.values( ))
            return dict([(u,float(minscore)/max(vsmall,l)) for (u,l) \
                in scores.items( )])
        else:
            maxscore=max(scores.values( ))
            if maxscore==0: maxscore=vsmall
            return dict([(u,float(c)/maxscore) for (u,c) in scores.items( )])

    def frequencyscore(self,rows):
        counts=dict([(row[0],0) for row in rows])
        for row in rows: counts[row[0]]+=1
        return self.normalizescores(counts)

    def locationscore(self,rows):
        locations=dict([(row[0],1000000) for row in rows])
        for row in rows:
            loc=sum(row[1:])
            if loc<locations[row[0]]: locations[row[0]]=loc

        return self.normalizescores(locations,smallIsBetter=1)

    def pagerankscore(self,rows):
        pageranks=dict([(row[0],self.con.execute('select score from pagerank where urlid=%d' % row[0]).fetchone( )[0]) for row in rows])
        maxrank=max(pageranks.values( ))
        normalizedscores=dict([(u,float(l)/maxrank) for (u,l) in \
                               pageranks.items( )])
        return normalizedscores