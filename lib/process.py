import sys
import time
import atexit
import threading
import multiprocessing
import signal
import logging

import selenium
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
import selenium.common.exceptions 

from bs4 import BeautifulSoup

from Config import Config
from modules import SearchDriver
from modules import URL
from modules import CustomLogging

class CrawlerPIDMgr(multiprocessing.managers.Namespace):
  def __init__(self):
    self.pid = dict()
  
  def setPid(self, processId, pid):
    self.pid[processId] = pid
  
  def getPid(self, processId):
    try:
      return self.pid[processId]
    except KeyError:
      return -1
      
  def getPidDict(self):
    return self.pid

def process (processId, chiefMgrConn, managers, urlQ, writerQ):
  if not chiefMgrConn:
    raise BaseException
  
  qEmptyTimeoutCnt = 0
  mainLogger = logging.getLogger('Linkbot')
  logger = logging.getLogger('Linkbot.Crawler')
  sys.stderr = CustomLogging.StreamToLogger(logger, logging.CRITICAL)
  config = managers[0].getConfig()
  CustomLogging.setLogConfig(mainLogger, config)
  keyword = managers[5].getKeyword()
  
  crawler = SearchDriver()
  managers[1].setPid(processId, crawler.service.process.pid)
  wait = WebDriverWait(crawler, timeout=0.1)
  
  # debug
  logger.info("Initiated")
  atexit.register(terminateDriver, crawler)
  cnt = 0
  try:
    while cnt < 500 and qEmptyTimeoutCnt < config.qEmptyTimeoutLimit:
      # config control
      try:
        if chiefMgrConn.poll(0.001):
          data = chiefMgrConn.recv().split()
          match data[0]:
            case "config":
              match data[1]:
                case "update":
                  config = managers[0].getConfig()
                  
                  # apply changed configuration
                  CustomLogging.setLogConfig(mainLogger, config)
                  logger.info("Configuration change applied")
                case _:
                  pass
            
            case "keyword":
              match data[1]:
                case "update":
                  keyword = managers[5].getKeyword()
                  
                  logger.info("keyword change applied")
                case _:
                  pass
            
            case _:
              pass
      except BrokenPipeError:
        break
      
      if urlQ.empty():
        qEmptyTimeoutCnt += 1
        time.sleep(1)
        continue
      qEmptyTimeoutCnt = 0
      url, depth = urlQ.get()
      
      try:
        crawler.execute_script("window.localStorage.clear();")  # 로컬 스토리지 비우기
        crawler.execute_script("window.sessionStorage.clear();")  # 세션 스토리지 비우기
        crawler.execute_script("document.cookie = '';")  # 쿠키 비우기
        crawler.execute_script("document.querySelectorAll('link[rel=\"stylesheet\"]').forEach(e => e.remove());")  # 스타일 시트 삭제
        crawler.execute_script("document.querySelectorAll('script').forEach(e => e.remove());")  # 스크립트 삭제
        crawler.execute_script("document.querySelectorAll('img').forEach(e => e.remove());")  # 이미지 삭제
        crawler.execute_script("document.querySelectorAll('iframe').forEach(e => e.remove());")  # iframe 삭제
      except (selenium.common.exceptions.JavascriptException,
              selenium.common.exceptions.TimeoutException):
        pass
      
      # if not managers[2].lookup(url): # 0: matched
      #   continue
      if not managers[4].acquire(processId, url):
        urlQ.put((url, depth))
        continue
      
      if managers[3].mutualCheck(url): # 1: matched
        managers[4].release(processId)
        continue
      
      cnt += 1
      if cnt % 20 == 0:
        logger.debug("Alive")
        terminateDriver(crawler)
        crawler = SearchDriver()
        managers[1].setPid(processId, crawler.service.process.pid)
        wait = WebDriverWait(crawler, timeout=0.1)
      
      try:
        crawler.implicitly_wait(1.5)
        crawler.get(url)
        
        if url != crawler.current_url:
          if "warning.or.kr" in crawler.current_url:
            # 유해 사이트 목록에 추가
            continue
          
          url = crawler.current_url
          if managers[3].mutualCheck(url):
            continue
      except selenium.common.exceptions.TimeoutException as e:
        logger.debug("Timeout: {}".format(url))
        managers[3].delete(url)
        urlQ.put((url, depth+1))
        continue
      except selenium.common.exceptions.InvalidSessionIdException as e:
        logger.warning("Invalid session id: {}".format(url))
        managers[3].delete(url)
        urlQ.put((url, depth+1))
        continue
      except selenium.common.exceptions.UnexpectedAlertPresentException:
        logger.debug("Can't access: {}".format(url))
        continue
      except ConnectionResetError:
        logger.debug("Connection Reset: {}".format(url))
        managers[3].delete(url)
        urlQ.put((url, depth+1))
        continue
      except selenium.common.exceptions.InvalidArgumentException:
        logger.debug("Invalid Argument: {}".format(url))
        continue
      except selenium.common.exceptions.StaleElementReferenceException:
        logger.debug("Not loaded element exists: {}".format(url))
        continue
      except selenium.common.exceptions.WebDriverException as e:
        if "net::ERR_CONNECTION_TIMED_OUT" in e.msg:
          logger.debug("Timeout: {}".format(url))
          managers[3].delete(url)
          urlQ.put((url, depth+1))
          continue
        elif "net::ERR_NAME_NOT_RESOLVED" in e.msg:
          logger.warning("Name Not Resolved: {}".format(url))
          continue
        elif ("net::ERR_INTERNET_DISCONNECTED" in e.msg or 
              "net::ERR_CONNECTION_RESET" in e.msg or
              "net::ERR_CONNECTION_CLOSED" in e.msg):
          logger.debug("Disconnected")
          managers[3].delete(url)
          urlQ.put((url, depth))
          break
        elif ("net::ERR_CONNECTION_REFUSED" in e.msg or
              "net::ERR_ADDRESS_UNREACHABLE" in e.msg):
          continue
        elif "cannot determine loading status" in e.msg:
          # chrome error
          continue
        else:
          raise e
      finally:
        managers[4].release(processId)
      
      sHost = URL.getProtocolHost(url)
      ############### Weights Calculation ################
      try:
        wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "a")))
      except selenium.common.exceptions.TimeoutException:
        pass
      
      page = crawler.page_source
      soup = BeautifulSoup(page, "html.parser")
      
      windowHandles = crawler.window_handles
      if len(windowHandles) > 1:
        for handle in windowHandles[1:]:
          crawler.switch_to.window(handle)
          crawler.close()
        
        crawler.switch_to.window(windowHandles[0])
      
      if depth > 0 or config.CheckZeroDepth:
        writerQ.put(url)
        # weight = 0
        # weight += keyword.cal("url", url)
        # weight += keyword.cal("page", page)
        # if weight >= config.KeyWeightLimit:
        #   유해 사이트 목록에 추가
        #   writerQ.put(url)
      
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
            
            if len(link) > 4 and link[:4].lower() != "http":
              if link[:2] == "//":
                link = "https:" + link
              elif link[0] in "/?":
                link = sHost + link
              else:
                link = sHost + '/' + link
            elif len(link) <= 4:
              link = sHost + link
            
            sharp = link.find('#')
            if sharp > -1:
              link = link[:sharp]
            
            if len(link) > 1 and link[-1] == '/':
              link = link[:-1]
            
            if not managers[3].lookup(link):
              urlQ.put((link, depth+1))
  except KeyboardInterrupt:
    managers[3].delete(url)
    urlQ.put((url, depth))
    pass
  except Exception as e:
    logger.critical("Unhandled Error: {}".format(url))
    managers[3].delete(url)
    urlQ.put((url, depth+1))
    raise e
  finally:
    managers[4].release(processId)
  ####################################################
  terminateDriver(crawler)
  logger.info("Terminated")

def terminateDriver(driver: SearchDriver):
  if driver:
    try:
      driver.quit()
    except:
      pass