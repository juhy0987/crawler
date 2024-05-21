from modules import Robots
from lib import SearchDriver
from lib import URL
if __name__=="__main__":
  url = "https://search.naver.com/search.naver?ie=utf8&where=nexearch&query=민희진"
  baseURL = URL.getProtocolHost(url)
  print(baseURL)
  
  robots = Robots.RobotsJudgement(baseURL)
  print(robots.patterns)
  print(robots.isAble(url))