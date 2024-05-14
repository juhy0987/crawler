import sys
import time
import pickle
import subprocess
import multiprocessing
import multiprocessing.managers
import copy
import base64
import logging

from query import oracQry
from Config import Config
from modules import CustomLogging
class Keyword(object):
  mainLogger = logging.getLogger('Linkbot')
  logger = logging.getLogger('Linkbot.Keyword')
  
  def __init__ (self):
    self.keywordDicts = dict()
    
    self.config = None
    
  def load(self, key, query):
    oracMgr = subprocess.Popen(["python", "oracMgr.py"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    data, errMsg = oracMgr.communicate(query.encode())
    self.logger.debug(errMsg.decode())
    conts = pickle.loads(data)
    
    if not len(conts):
      return -1

    tmpDict = dict()
    for keyNo, weight, keyHex in conts:
      try:
        keyword = base64.b64decode(keyHex).decode()
      except ValueError:
        continue
      
      try:
        curWeight = tmpDict[keyword]
      except KeyError:
        tmpDict[keyword] = weight
        continue
      
      if curWeight < weight:
        tmpDict[keyword] = weight
      
    self.keywordDicts[key] = tmpDict
    
    return 0
  
  def cal(self, dictKey, source):
    try:
      curDict = self.keywordDicts[dictKey]
    except KeyError:
      return -1
    
    weight = 0
    for key, value in curDict.items():
      if key in source:
        weight += value
    
    return weight

  def lookup(self, key):
    result = []
    for dictKey, curDict in self.keywordDicts.items():
      try:
        weight = curDict[key]
      except KeyError:
        pass
      else:
        result.append((dictKey, weight))
    return result

class KeywordMgr(multiprocessing.managers.Namespace):
  def __init__ (self, configMgr):
    self.keyword = Keyword()
    self.configMgr = configMgr
    self.keyword.config = configMgr.getConfig()
    CustomLogging.setLogConfig(self.keyword.mainLogger, self.keyword.config)
    
    baseQuery = oracQry.keywordDict["base"]
    if not self.keyword.load("page", baseQuery.format(self.keyword.config.KeyGID)):
      self.keyword.logger.info("Page Keyword loaded")
    if not self.keyword.load("url", baseQuery.format(self.keyword.config.URLKeyGID)):
      self.keyword.logger.info("URL Keyword loaded")
    
    self.updaterKillFlag = False
    self.updateFlag = False
    self.conn, cConn = multiprocessing.Pipe()
    self.updater = multiprocessing.Process(name="Keyword", target=self.autoUpdate, args=(cConn,), daemon=True)
    self.updater.start()
  
  def reviveUpdater(self):
    if not self.updater.is_alive():
      self.conn, cConn = multiprocessing.Pipe()
      self.updater = multiprocessing.Process(name="Keyword", target=self.autoUpdate, args=(cConn,), daemon=True)
      self.updater.start()
  
  def autoUpdate(self, conn):
    sys.stderr = CustomLogging.StreamToLogger(self.keyword.logger, logging.CRITICAL)
    while True:
      cnt = 0
      while cnt < self.keyword.config.KeywordLoadPeriod:
        if self.updaterKillFlag:
          sys.exit(0)
        
        try:
          if conn.poll(0.001):
            data = conn.recv().split()
            match data[0]:
              case "config":
                match data[1]:
                  case "update":
                    self.keyword.config = self.configMgr.getConfig()
                    
                    # apply changed configuration
                    CustomLogging.setLogConfig(self.keyword.mainLogger, self.keyword.config)
                    self.keyword.logger.info("Configuration change applied")
                  case _:
                    pass
              case  _:
                pass
        except BrokenPipeError:
          sys.exit(0)
        cnt += 1
        time.sleep(1)
      
      baseQuery = oracQry.keywordDict["base"]
      tmpKeyword = Keyword()
      tmpKeyword.config = self.keyword.config
      
      if not tmpKeyword.load("page", baseQuery.format(self.keyword.config.KeyGID)):
        self.keyword.logger.info("Page Keyword loaded")
      if not tmpKeyword.load("url", baseQuery.format(self.keyword.config.URLKeyGID)):
        self.keyword.logger.info("URL Keyword loaded")
      
      self.updateFlag = True
  
  def update(self):
    baseQuery = oracQry.keywordDict["base"]
    tmpKeyword = Keyword()
    tmpKeyword.config = self.keyword.config
    
    if not tmpKeyword.load("page", baseQuery.format(self.keyword.config.KeyGID)):
      self.keyword.logger.info("Page Keyword loaded")
    if not tmpKeyword.load("url", baseQuery.format(self.keyword.config.URLKeyGID)):
      self.keyword.logger.info("URL Keyword loaded")
    
    self.updateFlag = True
  
  def getUpdaterPID(self):
    if self.updater.is_alive():
      return self.updater.pid
    return -1
  
  def getKeyword(self):
    return copy.deepcopy(self.keyword)
  
  def changeConfig(self):
    self.conn.send("config update")
  
  def getUpdateFlag(self):
    return self.updateFlag

  def setUpdateFlag(self, value):
    self.updateFlag = value
  
  def get(self, keyword):
    return self.keyword.lookup(keyword)
  
if __name__=="__main__":
  import os
  try:
    os.remove("linkbot.pid")
  except:
    pass
  config = Config()
  config.load("./config/linkbot.conf")
  keywordMgr = KeywordMgr(config)
  keyword = keywordMgr.getKeyword()
  # print(keyword.keywordDicts["page"])
  
  while True:
    word = input(">> ").encode('utf-8')
    pageWeight = keyword.cal("page", word)
    urlWeight = keyword.cal("url", word)
    totalWeight = 0
    if not pageWeight < 0:
      totalWeight += pageWeight
    if not urlWeight < 0:
      totalWeight += urlWeight
    
    print(totalWeight)