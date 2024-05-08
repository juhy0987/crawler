import sys
import time
import pickle
import subprocess
import multiprocessing
import multiprocessing.managers

from query import oracQry
from Config import Config
from modules import URL
from modules.URLTree import URLTree
from modules.RegexURLTree import RegexTree

class JudgementTree(object):
  def __init__(self):
    self.queryDict = dict()
    self.treeDict = dict()

    self.config = None
  
  def init(self):
    self.queryDict = oracQry.treeDict
    self.treeDict.clear()
  
  def lookup(self, sURL):
    for key in self.treeDict.keys():
      if not self.treeDict[key].lookupURL(sURL):
        return 0
    return -1
  
  def updateAll(self):
    print("[Judgement Update] Tree Update", file=sys.stderr)
    sys.stderr = self.config.applyLog(sys.stderr)
    cnt = 0
    for key in self.queryDict.keys():
      if not self.update(key):
        print("[Judgement Update] Tree [{}] Updated".format(key), file=sys.stderr)
        sys.stderr = self.config.applyLog(sys.stderr)
        cnt += 1
    
    print("[Judgement Update] Tree Update Completed, Success: {}, Failed: {}".format(cnt, len(self.queryDict)-cnt), file=sys.stderr)
    sys.stderr = self.config.applyLog(sys.stderr)
  
  def update(self, key):
    oracMgr = subprocess.Popen(["python", "oracMgr.py"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    data, errMsg = oracMgr.communicate(self.queryDict[key][0].encode())
    # print(errMsg.decode(), file=sys.stderr)
    conts = pickle.loads(data)
    
    # print(len(conts))
    
    if not len(conts):
      return -1
    
    match self.queryDict[key][1]:
      case 0:
        tmpTree = URLTree()
      case 1:
        tmpTree = RegexTree()
      case _:
        print("[Judgement Update] Wrong Tree Type: {}".format(self.queryList[id][1]), file=sys.stderr)
        return -1
  
    if tmpTree.load(conts) < 0:
      return -1

    self.treeDict[key] = tmpTree
    return 0


class JudgementTreeMgr(multiprocessing.managers.Namespace):
  def __init__(self, sFilePath, configMgr):
    super().__init__()
    self.judgementTree = JudgementTree()
    self.sFilePath = sFilePath
    self.configMgr = configMgr
    self.judgementTree.config = configMgr.getConfig()
    
    self.judgementTree.init()
    self.judgementTree.updateAll()
    
    self.updaterKillFlag = False
    self.conn, cConn = multiprocessing.Pipe()
    self.updater = multiprocessing.Process(target=self.update, args=(cConn), daemon=True)
    self.updater.start()
  
  def lookup(self, sURL):
    if self.judgementTree.lookup(sURL) < 0:
      return -1
    return 0
  
  def reviveUpdater(self):
    if not self.updater.is_alive():
      self.conn, cConn = multiprocessing.Pipe()
      self.updater = multiprocessing.Process(target=self.update, args=(cConn), daemon=True)
      self.updater.start()
  
  def update(self, conn):
    sys.stderr = self.judgementTree.config.applyLog(sys.stderr)
    while True:
      time.sleep(self.judgementTree.config.DBUpdatePeriod)
      if self.updaterKillFlag:
        break
      
      try:
        if conn.poll(0.001):
          data = conn.recv().split()
          match data[0]:
            case "config":
              match data[1]:
                case "update":
                  self.judgementTree.config = self.configMgr.getConfig()
                  
                  # apply changed configuration
                  print("[Crawler] Process[{}] configuration change applied".format("judgement"), file=sys.stderr)
                case _:
                  pass
            case  _:
              pass
      except BrokenPipeError:
        break
        
      self.judgementTree.updateAll()
      
      sys.stderr = self.judgementTree.config.applyLog(sys.stderr)
      
  def getUpdaterPID(self):
    if self.updater.is_alive():
      return self.updater.pid
    return -1
  
  def changeConfig(self):
    self.conn.send("config update")

if __name__=="__main__":
  import os
  try:
    os.remove("linkbot.pid")
  except:
    pass
  config = Config()
  config.load("./config/linkbot.conf")
  treeMgr = JudgementTreeMgr("./config/oracdb.conf", config)
  
  while True:
    url = input("url >> ").split('\n')[0]
    if treeMgr.lookup(url) == 0:
      print("detected")
    else:
      print("Not detected")
