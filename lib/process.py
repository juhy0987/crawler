import sys, os
import time
import subprocess
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

def process (processId, chiefMgrConn, ping, managers, urlQ, writerQ):
  if not chiefMgrConn:
    raise BaseException
  
  try:
    qEmptyTimeoutCnt = 0
    mainLogger = logging.getLogger('Linkbot')
    logger = logging.getLogger('Linkbot.Crawler')
    sys.stderr = CustomLogging.StreamToLogger(logger, logging.CRITICAL)
    config = managers[0].getConfig()
    keyword = managers[5].getKeyword()
    
    CustomLogging.setLogConfig(mainLogger, config)
    
    crawler = SearchDriver()
    managers[1].setPid(processId, crawler.service.process.pid)
    wait = WebDriverWait(crawler, timeout=0.1)
    
    # debug
    logger.info("Initiated")
    cnt = 0
    while cnt < 500 and qEmptyTimeoutCnt < config.qEmptyTimeoutLimit:
      # config control
      if chiefMgrConn.poll(0):
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
            
      if not ping.poll(0):
        ping.send("l")

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
      except:
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
        crawler.implicitly_wait(config.PageLoadTimeoutLimit)
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
      except (ConnectionResetError, ConnectionRefusedError):
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
              "net::ERR_CONNECTION_CLOSED" in e.msg or
              "disconnected" in e.msg):
          logger.debug("Disconnected")
          managers[3].delete(url)
          urlQ.put((url, depth))
          break
        elif ("net::ERR_CONNECTION_REFUSED" in e.msg or
              "net::ERR_ADDRESS_UNREACHABLE" in e.msg):
          continue
        elif ("cannot determine loading status" in str(e) or
              "missing or invalid columnNumber" in str(e)):
          logger.warning("Too short time for loading this url: {}".format(url))
          continue
        else:
          raise e
      finally:
        managers[4].release(processId)
      
      windowHandles = crawler.window_handles
      if len(windowHandles) > 1:
        for handle in windowHandles[1:]:
          crawler.switch_to.window(handle)
          crawler.close()
        
        crawler.switch_to.window(windowHandles[0])
      
      sHost = URL.getProtocolHost(url)
      ############### Weights Calculation ################
      try:
        wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "a")))
      except selenium.common.exceptions.UnexpectedAlertPresentException:
        continue
      except selenium.common.exceptions.TimeoutException:
        pass
      
      page = crawler.page_source
      soup = BeautifulSoup(page, "html.parser")
      
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
              if link[0] in '/?':
                link = sHost + link
              else:
                link = sHost + '/' + link
            
            sharp = link.find('#')
            if sharp > -1:
              link = link[:sharp]
            
            if len(link) > 1 and link[-1] == '/':
              link = link[:-1]
            
            if not managers[3].lookup(link):
              urlQ.put((link, depth+1))
  except (KeyboardInterrupt, BrokenPipeError):
    managers[3].delete(url)
    urlQ.put((url, depth))
  except Exception as e:
    logger.critical("Unhandled Error: {}".format(url))
    managers[3].delete(url)
    urlQ.put((url, depth))
    raise e
  finally:
    managers[4].release(processId)
    logger.debug("After release: {}".format(processId))
    try:
      chiefMgrConn.close()
    except:
      pass
    try:
      ping.close()
    except:
      pass
    try:
      crawler.service.process.terminate()
      pid = crawler.service.process.pid
      if sys.platform == 'win32':
        p = subprocess.Popen(["taskkill", "/pid", str(pid), "/t", "/f"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      elif sys.platform == 'linux':
        p = subprocess.Popen(["pkill", "-9", "-P", str(pid)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except:
      pass
    sys.stderr = CustomLogging.StreamToLogger(logger, logging.DEBUG)
  ####################################################
  
  logger.info("Terminated")
  
  sys.exit(0)
  
def writerProcess(id, chiefConn, configMgr, q):
  mainLogger = logging.getLogger('Linkbot')
  logger = logging.getLogger('Linkbot.Writer')
  writer = logging.getLogger('Writer')
  
  config = configMgr.getConfig()
  CustomLogging.setLogConfig(mainLogger, config)
  writer.setLevel(logging.INFO)
  writer.addHandler(logging.FileHandler(config.URLLogFilePath))
  
  cnt = 0
  tStart = time.time()
  while True:
    if chiefConn.poll(0.01):
      data = chiefConn.recv()
      try:
        data = data.split()
        match data[0]:
          case "config":
            match data[1]:
              case "update":
                config = configMgr.getConfig()
                
                # apply changed configuration
                CustomLogging.setLogConfig(mainLogger, config)
                logger.info("Configuration change applied")
              case _:
                pass
          case _:
            pass
      except Exception as e:
        logger.error(str(e))
    
    
    while not q.empty():
      writer.info(q.get())
      cnt += 1
    if cnt % 1000 == 0:
      tEnd = time.time()
      writer.debug("Elapsed time: {}\n".format(tEnd-tStart))
      writer.debug("{}!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n\n\n\n\n\n".format(cnt))
    time.sleep(1)

def showInfo():
  print("""
########### Linkbot Command Information ###########
config(c)
- update(u): update configuration object from current configuration file
- get(g) 'CONFIG': if 'CONFIG' in current configuration return set value, else None

keyword(k)
- update(u): update keyword object from current DB
- get(g) 'KEYWORD': if 'keyword' in DB return weight, else None

tree(t)
- update(u) : update Judgement Tree from DB
- lookup(l) 'url': if 'url' in Judgement Tree return True, else False

duplicate(d) 'URL': check if 'URL' in duplication exclude DB 

lock(l)
- url(u) 'URL': if 'URL' has lock in semaphore return such process id, else return None
- id(i) 'ID': if 'ID' using semaphore return using 'URL', else None
- all(a): show all semaphore allocate

queue(q): return current queue size

process(p)
- check(c) 'ID': show if process 'ID' is alive, if no such ID return None
- show(s) ['alive', 'dead', 'all'(default)]: 
- kill(k) ['error', 'soft', 'hard'] 'ID': kill process 'ID'
  'error': By Exception
  'soft': By Keyboard Interrupt Signal
  'hard': Immediate 
- number(n): show currently running processes

insert(i) 'URL': insert 'URL' to start URL Q

exit(x)
: Terminate the Linkbot""")

def terminateDriver(driver):
  if driver:
    try:
      driver.quit()
    except:
      pass
