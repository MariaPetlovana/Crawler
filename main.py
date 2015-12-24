__author__ = 'Masha'

from searchengine import *

def main():
    cr = crawler('searchindex.db')
    cr.createindextables()

    with open("pages.txt") as file:
        pages = [line.rstrip('\n') for line in file]

    file.close()

    cr.crawl(pages)
    cr.calculatepagerank()

    e=searcher('searchindex.db')
    print(e.query('paradigm'))

if __name__ == "__main__":
    main()