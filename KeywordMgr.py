import sys
import time
import pickle
import subprocess
import multiprocessing
import multiprocessing.managers
import copy
import base64

from query import oracQry
from Config import Config

class Keyword(object):
  def __init__ (self):
    self.keywordDicts = dict()
    
    self.config = None
    
  def load(self, key, query):
    oracMgr = subprocess.Popen(["python", "oracMgr.py"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # print(query)
    data, errMsg = oracMgr.communicate(query.encode())
    # print(errMsg.decode(), file=sys.stderr)
    conts = pickle.loads(data)
    
    if not len(conts):
      return -1

    tmpDict = dict()
    for keyNo, weight, keyHex in conts:
      try:
        keyword = base64.b64decode(keyHex)
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

class KeywordMgr(multiprocessing.managers.Namespace):
  def __init__ (self, configMgr):
    self.keyword = Keyword()
    self.configMgr = configMgr
    self.keyword.config = configMgr.getConfig()
    
    baseQuery = oracQry.keywordDict["base"]
    if not self.keyword.load("page", baseQuery.format(self.keyword.config.KeyGID)):
      print("[Keyword Load] Page Keyword dict loaded", file=sys.stderr)
    if not self.keyword.load("url", baseQuery.format(self.keyword.config.URLKeyGID)):
      print("[Keyword Load] URL Keyword dict loaded", file=sys.stderr)
    sys.stderr = self.keyword.config.applyLog(sys.stderr)
    
    self.updaterKillFlag = False
    self.updateFlag = False
    self.conn, cConn = multiprocessing.Pipe()
    self.updater = multiprocessing.Process(target=self.update, args=(cConn), daemon=True)
    self.updater.start()
  
  def reviveUpdater(self):
    if not self.updater.is_alive():
      self.conn, cConn = multiprocessing.Pipe()
      self.updater = multiprocessing.Process(target=self.update, args=(cConn), daemon=True)
      self.updater.start()
  
  def update(self, conn):
    while True:
      time.sleep(self.keyword.config.KeywordLoadPeriod)
      if self.updaterKillFlag:
        break
      
      try:
        if conn.poll(0.001):
          data = conn.recv().split()
          match data[0]:
            case "config":
              match data[1]:
                case "update":
                  self.keyword.config = self.configMgr.getConfig()
                  
                  # apply changed configuration
                  print("[Crawler] Process[{}] configuration change applied".format("judgement"), file=sys.stderr)
                case _:
                  pass
            case  _:
              pass
      except BrokenPipeError:
        break
      
      baseQuery = oracQry.keywordDict["base"]
      tmpKeyword = Keyword()
      tmpKeyword.config = self.keyword.config
      
      if not tmpKeyword.load("page", baseQuery.format(self.keyword.config.KeyGID)):
        print("[Keyword Update] Page Keyword dict loaded", file=sys.stderr)
      if not tmpKeyword.load("url", baseQuery.format(self.keyword.config.URLKeyGID)):
        print("[Keyword Update] URL Keyword dict loaded", file=sys.stderr)
      
      sys.stderr = self.keyword.config.applyLog(sys.stderr)
      
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