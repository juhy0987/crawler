import sys, os
import time
import multiprocessing
import logging
import socket
from urllib.parse import urljoin

import selenium
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
import selenium.common.exceptions 

from bs4 import BeautifulSoup

from lib import SearchDriver
from lib import URL
from lib import CustomLogging
from lib import procSig

from . import ConfigMgr
from . import Robots

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
    
    crawler = SearchDriver.SearchDriver()
    managers[1].setPid(processId, crawler.service.process.pid)
    wait = WebDriverWait(crawler, timeout=0.1)
    
    # debug
    logger.info("Initiated")
    cnt = 0
    while cnt < 500 and qEmptyTimeoutCnt < config.qEmptyTimeoutLimit:
      # config control
      while chiefMgrConn.poll(0):
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
            
      ping.send("l")

      if not urlQ.qsize():
        qEmptyTimeoutCnt += 1
        time.sleep(1)
        continue
      url, depth = urlQ.get()
      if depth > config.MaxDepth:
        managers[3].mutualCheck(url)
        continue
      qEmptyTimeoutCnt = 0
      
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
      
      if not managers[2].lookup(url, ["filter_white_url"]): # 0: matched
        continue
        
      if config.CheckRobot:
        robots = Robots.RobotsJudgement(URL.getProtocolHost(url))
        if not robots.isAble(url): # True: can crawl
          logger.debug(f"Robot cannot access: {url}")
          continue
      
      if not managers[4].acquire(processId, url):
        urlQ.forcePut((url, depth))
        continue
      
      if managers[3].mutualCheck(url): # 1: matched
        managers[4].release(processId)
        continue
      
      cnt += 1
      if cnt % 20 == 0:
        logger.debug("Alive")
        terminateDriver(crawler)
        crawler = SearchDriver.SearchDriver()
        managers[1].setPid(processId, crawler.service.process.pid)
        wait = WebDriverWait(crawler, timeout=0.1)
      
      try:
        try:
          ip = socket.gethostbyname(URL.getHost(url))
        except socket.gaierror:
          logger.warning(f"DNS not found: {url}")
          continue
        
        crawler.implicitly_wait(config.PageLoadTimeoutLimit)
        crawler.get(url)
        
        if url != crawler.current_url:
          tmpToken = URL.tokenize(crawler.current_url)
          if ["kr", "or", "warning"] == tmpToken[:3]:
            writerQ.put((url, "warn", []))
            continue
          
          url = crawler.current_url
          
          if config.CheckRobot:
            robots = Robots.RobotsJudgement(URL.getProtocolHost(url))
            if not robots.isAble(url): # True: can crawl
              logger.debug(f"Robot cannot access: {url}")
              continue
          
          if not managers[2].lookup(url, ["filter_white_url"]): # 0: matched
            continue
          if managers[3].mutualCheck(url):
            continue
      except selenium.common.exceptions.TimeoutException as e:
        logger.debug("Timeout: {}".format(url))
        managers[3].delete(url)
        urlQ.forcePut((url, depth*2+1))
        continue
      except selenium.common.exceptions.InvalidSessionIdException as e:
        logger.warning("Invalid session id: {}".format(url))
        managers[3].delete(url)
        urlQ.forcePut((url, depth*2+1))
        continue
      except selenium.common.exceptions.StaleElementReferenceException:
        logger.debug("Not loaded element exists: {}".format(url))
        managers[3].delete(url)
        urlQ.forcePut((url, depth*2+1))
        continue
      except ConnectionResetError:
        logger.debug("Connection Reset: {}".format(url))
        managers[3].delete(url)
        urlQ.forcePut((url, depth*2+1))
        continue
      except (selenium.common.exceptions.UnexpectedAlertPresentException,
              selenium.common.exceptions.NoSuchElementException,
              ConnectionRefusedError):
        logger.debug("Can't access: {}".format(url))
        continue
      except selenium.common.exceptions.InvalidArgumentException:
        logger.debug("Invalid Argument: {}".format(url))
        continue
      except selenium.common.exceptions.WebDriverException as e:
        if ("net::ERR_CONNECTION_TIMED_OUT" in e.msg or 
            "cannot determine loading status" in str(e) or
            "missing or invalid columnNumber" in str(e)):
          logger.warning("Timeout: {}".format(url))
          managers[3].delete(url)
          urlQ.forcePut((url, depth*2+1))
          continue
        elif "no such execution context" in e.msg:
          logger.warning("Script Error: {}".format(url))
          urlQ.forcePut((url, depth*2+1))
          continue
        elif ("net::ERR_CONNECTION_RESET" in e.msg or 
              "net::ERR_SSL_PROTOCOL_ERROR" in e.msg or
              "net::ERR_SSL_VERSION_OR_CIPHER_MISMATCH" in e.msg):
          logger.debug("SSL_ERROR: {}".format(url))
          managers[3].delete(url)
          urlQ.forcePut((url, depth*2+1))
          continue
        elif ("net::ERR_INTERNET_DISCONNECTED" in e.msg or
              "net::ERR_CONNECTION_CLOSED" in e.msg or
              "disconnected" in e.msg or 
              "session not created" in e.msg):
          logger.debug("Disconnected")
          managers[3].delete(url)
          urlQ.forcePut((url, depth))
          break
        elif "net::ERR_NAME_NOT_RESOLVED" in e.msg:
          logger.warning("Name Not Resolved: {}".format(url))
          continue
        elif ("net::ERR_CONNECTION_REFUSED" in e.msg or
              "net::ERR_ADDRESS_UNREACHABLE" in e.msg or
              "unexpected alert open" in e.msg):
          logger.debug("Can't access: {}".format(url))
          continue
        else:
          logger.critical("Unhandled Error: {} {}".format(url, str(e)))
          managers[3].delete(url)
          urlQ.forcePut((url, depth*2+1))
          continue
      except KeyboardInterrupt:
        raise KeyboardInterrupt
      except Exception as e:
        logger.critical("Unhandled Error: {} {}".format(url, str(e)))
        managers[3].delete(url)
        urlQ.forcePut((url, depth*2+1))
        continue
      finally:
        managers[4].release(processId)
      
      ping.send("l")
      
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
      
      # Judge threaten Weight
      if (depth > 0 or config.CheckZeroDepth) and managers[2].lookupAll(url):
        weight = 0
        detectedList = []
        urlWeight, detectedURLKey = keyword.cal("url", url)
        pageWeight, detectedPageKey = keyword.cal("page", page)
        weight += urlWeight + pageWeight
        detectedList += detectedURLKey + detectedPageKey
        if urlWeight >= config.KeyWeightLimit:
          writerQ.put((url, "url", detectedURLKey))
        elif pageWeight >= config.KeyWeightLimit:
          writerQ.put((url, "page", detectedPageKey))
        elif weight >= config.KeyWeightLimit:
          writerQ.put(url, "total", detectedList)
      
      ping.send("l")
      ############### Next Link Crawling ##################
      if depth < config.MaxDepth:
        tag_a = soup.select('a')
          
        for tag in tag_a:
          ping.send("l")
          try:
            link = tag['href']
          except KeyError:
            continue
          
          if link:
            try:
              if len(link) > 10 and link[:10].lower() == "javascript":
                continue
              
              sharp = link.find('#')
              if sharp > -1:
                link = link[:sharp]
              
              link = link.strip()
              if not link or link[-1] != "/":
                link += "/"
              
              if len(link) > 4 and "go" in link[:3]:
                link = "https://" + link[3:]
              else:
                link = urljoin(sHost.strip(), link.strip())
              
              if not managers[2].lookup(url, ["filter_white_url"]): # 0: matched 
                continue
              
              if not managers[3].lookup(link):
                urlQ.put((link, depth+1))
            except IndexError:
              logger.warning(f"Wrong parse format: {link}")
              pass
  except (KeyboardInterrupt, BrokenPipeError):
    try:
      managers[3].delete(url)
    except (BrokenPipeError, EOFError):
      pass
    logger.info("Received exit signal")
    try:
      urlQ.forcePut((url, depth*2+1))
    except (BrokenPipeError, EOFError):
      pass
    sys.exit(0)
  except Exception as e:
    logger.critical("Unhandled Error: {} {}".format(url, str(e)))
    managers[3].delete(url)
    urlQ.forcePut((url, depth*2+1))
    raise e
  finally:
    try:
      managers[4].release(processId)
    except (BrokenPipeError, EOFError):
      pass
    logger.debug("After release: {}".format(processId))
    try:
      pid = crawler.service.process.pid
      procSig.killFamilyByPID(pid)
    except:
      pass
    sys.stderr = CustomLogging.StreamToLogger(logger, logging.DEBUG)
    try:
      ping.send("d")
    except:
      pass
  ####################################################
  
  if cnt >= 500:
    logger.info("Terminated: Restart Crawler for resource")
  elif qEmptyTimeoutCnt >= config.qEmptyTimeoutLimit:
    logger.info("Terminated: No URL in Q")
  else:
    logger.info("Terminated: Disconnected ")
  
  sys.exit(0)
  
def writerProcess(id, chiefConn, configMgr, q):
  mainLogger = logging.getLogger('Linkbot')
  logger = logging.getLogger('Linkbot.Writer')
  writer = logging.getLogger('Writer')
  
  config = configMgr.getConfig()
  CustomLogging.setLogConfig(mainLogger, config)
  writer.setLevel(logging.INFO)
  writer.addHandler(logging.FileHandler(config.URLLogFilePath))
  
  try:
    while True:
      if chiefConn.poll(0):
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
        except BrokenPipeError:
          sys.exit(0)
      
      while q.qsize():
        url, detectedSrcType, detectedKeyword = q.get()
        writer.info(f"{url} {detectedSrcType} {detectedKeyword}")
      time.sleep(1)
  except KeyboardInterrupt:
    sys.exit(0)

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
