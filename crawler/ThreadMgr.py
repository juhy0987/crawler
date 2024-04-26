import sys, os
import time
import threading

import selenium
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By

sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
from Config import Config
from modules import SearchDriver

def thread(id, config, managers, urlQ, writerQ):
  localData = threading.local()
  
  localData.crawler = SearchDriver()
  localData.wait = WebDriverWait(localData.crawler, timeout=5)
  while not urlQ.empty():
    sys.stderr = config.applyLog(sys.stderr)
    tmpData = threading.local()
    tmpData.url, tmpData.depth = urlQ.get()

    # print("Thread[{}] Running".format(id), file=sys.__stdout__)
    
    if managers[2].mutualCheck(tmpData.url):
      continue
    
    try:
      localData.crawler.get(tmpData.url)
    except selenium.common.exceptions.WebDriverException as e:
      if "net::ERR_CONNECTION_TIMED_OUT" in e.msg:
        print("[Crawler Load] TIMED OUT: {}".format(tmpData.url), file=sys.stderr)
        continue
      elif "invalid session id" in e.msg:
        print("[Crawler Load] Invalid session id(Bot Detected): {}".format(tmpData.url), file=sys.stderr)
        continue
      else:
        print("[Crawler Load] Unhandled Error: {}'\n: {}".format(e.msg, tmpData.url), file=sys.stderr)
        raise e
    except selenium.common.exceptions.InvalidSessionIdException as e:
      if "invalid session id" in e.msg:
        print("[Crawler Load] Invalid session id(Bot Detected): {}".format(tmpData.url), file=sys.stderr)
        continue
      else:
        print("[Crawler Load] Unhandled Error: {}'\n: {}".format(e.msg, tmpData.url), file=sys.stderr)
        raise e
    except Exception:
      print("[Crawler Load] Unhandled Error: {}'\n: {}".format(e.msg, tmpData.url), file=sys.stderr)
      raise e
    
    
    ############### Weights Calculation ################
    # if tmpData.depth > 0 or config.CheckZeroDepth:
            
    ####################################################
    writerQ.put(tmpData.url)
    if tmpData.depth < config.MaxDepth:
      tmpData.links = []
      try:
        localData.wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "a")))
      except selenium.common.exceptions.TimeoutException:
        print("[Crawler Load] Link TIMED OUT: {}".format(tmpData.url), file=sys.stderr)
        continue
      tmpData.tag_a = localData.crawler.find_elements(By.TAG_NAME, "a")
      for tag in tmpData.tag_a:
        # link = tag.get_attribute('href')
        try:
          tmpData.link = localData.wait.until(EC.visibility_of(tag)).get_attribute('href')
        except selenium.common.exceptions.TimeoutException:
          print("[Crawler Load] href TIMED OUT: {}".format(tmpData.url), file=sys.stderr)
          continue
        except selenium.common.exceptions.StaleElementReferenceException:
          print("[Crawler Load] href TIMED OUT: {}".format(tmpData.url), file=sys.stderr)
          continue
        
        if tmpData.link:
          tmpData.sharp = tmpData.link.find('#')
          if tmpData.sharp > -1:
            tmpData.link = tmpData.link[:tmpData.sharp]
          
          if len(tmpData.link) > 1 and tmpData.link[-1] == '/':
            tmpData.link = tmpData.link[:-1]
          
          if len(tmpData.link) > 10 and tmpData.link[:10] == "javascript":
            continue
          
          if not managers[2].lookup(tmpData.link):
            urlQ.put((tmpData.link, tmpData.depth+1))

class ThreadMgr(object):
  def __init__(self, maxThread=0):
    self.threads = dict()
    self.psNum = [ False ] * maxThread
    self.maxThread = maxThread
    
  def addThread(self, target, args):
    if len(self.threads) >= self.maxThread:
      return None

    id = self.getUnusedNum()
    if id < 0:
      return None
    args = (id, ) + args
    newThread = threading.Thread(name=str(id), target=target, args=args, daemon=True)
    
    if not newThread:
      return None

    self.threads[id] = newThread
    newThread.start()
    return id
  
  def getThread(self, id):
    try:
      return self.threads[id]
    except KeyError:
      return None
  
  def isThreadAlive(self, id):
    try:
      tmp = self.threads[id]
    except KeyError:
      return False
    else:
      pass
    
    return tmp.is_alive()
  
  def delThread(self, id):
    try:
      del(self.threads[id])
    except KeyError:
      pass
  
  def setUnusedNum(self, id):
    self.psNum[id] = False
  
  def getUnusedNum(self):
    if False in self.psNum:
      tmp = self.psNum.index(False)
      self.psNum[tmp] = True
      return tmp
    return -1

  def setMaxThread(self, num):
    self.maxThread = num

if __name__=="__main__":
  pass