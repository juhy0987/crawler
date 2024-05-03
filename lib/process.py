import sys
import time
import atexit
import threading
import multiprocessing
import signal

import selenium
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By

from bs4 import BeautifulSoup

from Config import Config
from modules import SearchDriver
from modules import URL

class CrawlerPIDMgr(multiprocessing.managers.Namespace):
  def __init__(self):
    self.pid = dict()
  
  def setPid(self, processId, pid):
    self.pid[processId] = pid
  
  def getPid(self):
    return self.pid

def process (processId, chiefMgrConn, managers, urlQ, writerQ):
  if not chiefMgrConn:
    raise BaseException
  
  qEmptyTimeoutCnt = 0
  config = managers[0].getConfig()
  sys.stderr = config.applyLog(sys.stderr)
  crawler = None
  
  # debug
  print("[Crawler Load] Process[{}] Initiated ".format(processId), file=sys.stderr)
  signal.signal(signal.SIGINT, sigIntHanlder)
  atexit.register(closeDriver, crawler)
  cnt = 0
  while qEmptyTimeoutCnt < config.qEmptyTimeoutLimit:
    # config control
    sys.stderr = config.applyLog(sys.stderr)
    if chiefMgrConn.poll(0.01):
      data = chiefMgrConn.recv()
      try:
        data = data.split()
        match data[0]:
          case "C":
            match data[1]:
              case "U":
                config = managers[0].getConfig()
                
                # apply changed configuration
                print("[Crawler] Process[{}] configuration change applied".format(processId), file=sys.stderr)
              case _:
                pass
          case _:
            pass
      except Exception as e:
        print("[Crawler Insite] Error occured: {}".format(str(e)), file=sys.__stdout__)
    # debug
    # print("Process[{}] {} Threads Running".format(processId, len(threadMgr.threads)), file=sys.__stdout__)
    
    
    cnt = (cnt + 1) % 100  
    if not cnt:
      print("[Crawler] Process[{}] Alive".format(processId), file=sys.stderr)
    if urlQ.empty():
      qEmptyTimeoutCnt += 1
      time.sleep(1)
      continue
    qEmptyTimeoutCnt = 0
    url, depth = urlQ.get()
    closeDriver(crawler)
    crawler = SearchDriver()
    managers[3].setPid(processId, crawler.service.process.pid)
    wait = WebDriverWait(crawler, timeout=0.1)
    
    # print(url, depth)
    
    if not managers[4].acquire(url):
      urlQ.put((url, depth))
      continue
    
    # if not managers[1].lookup(url): # 0: matched
    #   continue
    
    if managers[2].mutualCheck(url): # 1: matched
      managers[4].release(url)
      continue
    
    try:
      crawler.get(url)
      crawler.implicitly_wait(1.5)
    except selenium.common.exceptions.WebDriverException as e:
      managers[4].release(url)
      if "net::ERR_CONNECTION_TIMED_OUT" in e.msg:
        print("[Crawler Load] TIMED OUT: {}".format(url), file=sys.stderr)
        urlQ.put((url, depth+1))
        managers[2].delete(url)
        continue
      elif "invalid session id" in e.msg:
        print("[Crawler Load] Invalid session id: {}".format(url), file=sys.stderr)
        urlQ.put((url, depth+1))
        managers[2].delete(url)
        continue
      elif "net::ERR_NAME_NOT_RESOLVED" in e.msg:
        print("[Crawler Load] Name Not Resolved: {}".format(url), file=sys.stderr)
        continue
      elif "net::ERR_INTERNET_DISCONNECTED" in e.msg:
        urlQ.put((url, depth))
        managers[2].delete(url)
        continue
      else:
        print("[Crawler Load] Unhandled Error: {}: {}".format(e.msg, url), file=sys.stderr)
        raise e
    except selenium.common.exceptions.InvalidSessionIdException as e:
      managers[4].release(url)
      if "invalid session id" in e.msg:
        print("[Crawler Load] Invalid session id(Bot Detected): {}".format(url), file=sys.stderr)
        urlQ.put((url, depth+1))
        managers[2].delete(url)
        continue
      else:
        print("[Crawler Load] Unhandled Error: {}: {}".format(e.msg, url), file=sys.stderr)
        raise e
    except selenium.common.exceptions.UnexpectedAlertPresentException:
      pass
    except Exception as e:
      managers[4].release(url)
      print("[Crawler Load] Unhandled Error: {}: {}".format(e, url), file=sys.stderr)
      raise e

    managers[4].release(url)
    if url != crawler.current_url:
      if "warning.or.kr" in crawler.current_url:
        # 유해 사이트 목록에 추가
        continue
      
      url = crawler.current_url
      if managers[2].mutualCheck(url):
        continue
    
    sHost = URL.getProtocolHost(url)
    ############### Weights Calculation ################
    try:
      wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "a")))
    except selenium.common.exceptions.TimeoutException:
      pass
    
    page = crawler.page_source
    soup = BeautifulSoup(page, "html.parser")
    
    if depth > 0 or config.CheckZeroDepth:
      writerQ.put(url)
    
    ############### Next Link Crawling ##################
    if depth < config.MaxDepth:
      tag_a = soup.select('a')
        
      for tag in tag_a:
        try:
          link = tag['href']
        except KeyError:
          continue
        
        if link:
          if len(link) > 10 and link[:10] == "javascript":
            continue
          
          if link[:4].lower() != "http":
            link = sHost + link
          
          sharp = link.find('#')
          if sharp > -1:
            link = link[:sharp]
          
          if len(link) > 1 and link[-1] == '/':
            link = link[:-1]
          
          if not managers[2].lookup(link):
            urlQ.put((link, depth+1))
    ####################################################
  
def sigIntHanlder(signal, frame):
  print("[Crawler] Process Terminated", file=sys.stderr)
  sys.exit(0)

def closeDriver(driver):
  if driver:
    try:
      driver.close()
    except:
      pass
    try:
      driver.quit()
    except:
      pass