import sys, os
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
  keyword = managers[5].getKeyword()
  
  CustomLogging.setLogConfig(mainLogger, config)
  
  crawler = SearchDriver()
  managers[1].setPid(processId, crawler.service.process.pid)
  wait = WebDriverWait(crawler, timeout=0.1)
  
  # debug
  logger.info("Initiated")
  cnt = 0
  try:
    while cnt < 500 and qEmptyTimeoutCnt < config.qEmptyTimeoutLimit:
      # config control
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
    urlQ.put((url, depth+1))
    raise e
  finally:
    managers[4].release(processId)
    logger.debug("After release: {}".format(processId))
    terminateDriver(crawler)
    try:
      os.kill(crawler.service.process.pid, signal.SIGINT)
    except:
      pass
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
- number(n): show currently running processes

insert(i) 'URL': insert 'URL' to start URL Q

exit(x)
: Terminate the Linkbot""")


def console(commands, managers, processMgr, urlQ):
  while True:
    try:
      cmd = input("Linkbot >>> ")
      if not cmd:
        continue
      
      cmd = cmd.split()
      match cmd[0].lower():
        case letter if letter in ("exit", "x"):
          commands.put("x")
          for id, child in processMgr.children.items():
            os.kill(child.pid, signal.SIGINT)
          break
        
        case letter if letter in ("queue", "q"):
          print("queue size: {}".format(urlQ.qsize()))
          
        case letter if letter in ("config", "c"):
          match cmd[1].lower():
            case letter if letter in ("update", "u"):
              managers[0].update()
            case letter if letter in ("get", "g"):
              result = managers[0].get(cmd[2])
              if result is None:
                print("No configuration option named [{}]".format(cmd[2]))
              else:
                print("{}: {}".format(cmd[2], result))
            case _:
              showInfo()
              
        case letter if letter in ("tree", "t"):
          match cmd[1].lower():
            case letter if letter in ("update", "u"):
              try:
                if not managers[2].update(cmd[2]):
                  print("Update Successful")
                else:
                  print("Update Failed")
              except IndexError:
                managers[2].updateAll()
            case letter if letter in ("lookup", "l"):
              result = managers[2].lookupDetail(cmd[2])
              if not result:
                print("No matched")
              else:
                print("Matched DBs:", result)
            case _:
              showInfo()
              
        case letter if letter in ("duplicate", "d"):
          if managers[3].lookup(cmd[1]):
            print('Passed')
          else:
            print('Not Passed')
            
        case letter if letter in ("lock", "l"):
          match cmd[1].lower():
            case letter if letter in ("url", "u"):
              result = managers[4].showURL(cmd[2])
              if not result:
                print("No work for URL: [{}]".format(cmd[2]))
              else:
                print("Currently using process:", result[1])
                print("Left semaphore: {}".format(result[0]))
            case letter if letter in ("id", "i"):
              print("ID: {} - {}".format(cmd[2], managers[4].showID(int(cmd[2]))))
            case letter if letter in ("all", "a"):
              locker, left = managers[4].showAll()
              print("######### Locker #########")
              for id, url in locker:
                print("ID: {} - {}".format(id, url))
              
              if left:
                print("\n##### useless semaphore #####")
                for url in left:
                  print(url)
            case _:
              showInfo()
            
        case letter if letter in ("keyword", "k"):
          match cmd[1].lower():
            case letter if letter in ("update", "u"):
              managers[5].update()
            case letter if letter in ("get", "g"):
              result = managers[5].get(cmd[2])
              if not result:
                print("No matched keyword: {}".format(cmd[2]))
                continue
              for key, weight in result:
                print("Category type: {}, Weight: {}".format(key, weight))
            case _:
              showInfo()
              
        case letter if letter in ("process", "p"):
          match cmd[1].lower():
            case letter if letter in ("check", "c"):
              status = processMgr.showProcess(int(cmd[2]))
              if status is None:
                print("ID: {} - Not allocated".format(cmd[2]))
              elif status:
                print("ID: {} - alive".format(cmd[2]))
              else:
                print("ID: {} - dead".format(cmd[2]))
            case letter if letter in ("show", "s"):
              try:
                if not processMgr.showProcesses(cmd[2].lower()):
                  showInfo()
              except IndexError:
                processMgr.showProcesses('all')
            case letter if letter in ("number", "n"):
              print("Number of processes: {}".format(processMgr.getProcessNum()))
        
        case letter if letter in ("insert", "i"):
          urlQ.put(cmd[1])
        
        case letter if letter in ("help", "h"):
          showInfo()
          
        case _:
          showInfo()
    
    except KeyboardInterrupt:
      break
    except (IndexError, ValueError):
      showInfo()

def terminateDriver(driver: SearchDriver):
  if driver:
    try:
      driver.quit()
    except:
      pass