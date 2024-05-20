import re

import requests
import urllib.parse
from urllib.parse import urljoin

class RobotsJudgement(object):
  def __init__ (self, baseURL):
    self.patterns = dict()
    self.load(baseURL)
    
  def load(self, baseURL):
    if not baseURL:
      return False
    
    try:
      response = requests.get(urljoin(baseURL, "/robots.txt"))
      response.raise_for_status()
      robots = response.text
    except requests.RequestException as e:
      return True
    
    print(robots)
    self.parse(robots)
      
    return True
  
  def parse(self, robots):
    options = robots.split('\n')
    flag = False
    for option in options:
      try:
        isAllow, dir = option.split(':', 1)
      except ValueError:
        continue
      
      isAllow = isAllow.strip().lower()
      dir = dir.strip()
      if not flag:
        if isAllow == "user-agent" and dir == "*":
          flag = True
        continue
      
      if isAllow == "user-agent" and dir != "*":
        break
      
      if isAllow == "disallow":
        isAllow = False
      elif isAllow == "allow":
        isAllow = True
      
      pattern = re.sub(r'\?', r'\\?', dir)
      pattern = re.sub(r'\*', r'.*', pattern)
      self.patterns[pattern] = isAllow
  
  def isAble(self, sURL):
    if len(sURL) > 7 and sURL[:4].lower() == 'http':
      sURL = sURL[6:]
      while sURL[0] in ':/':
        sURL = sURL[1:]

    if '#' in sURL:
      sURL = sURL.split('#')[0]
    
    if not sURL:
      return False

    path = "/" + sURL.split('/', 1)[1]
    isAllow = True
    for dir in self.patterns.keys():
      if re.match(dir, path):
        # print(f"matched: {dir}")
        isAllow = self.patterns[dir]
    return isAllow

if __name__=="__main__":
  baseURL = "https://www.naver.com/"
  url = "https://www.naver.com/"
  # print(re.match("/$", "/"))
  
  robots = RobotsJudgement(baseURL)
  print(robots.patterns)
  print(robots.isAble(url))