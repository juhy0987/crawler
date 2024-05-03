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
    self.dns_tns = None
    self.pool = None
    
    self.HostIP = ""
    self.Sid = ""
    self.Port = 0
    self.ID = ""
    self.Password = ""
    self.Min = 0
    self.Max = 2
    
    self.DBUpdatePeriod = 10
    
    self.config = None
  
  def init(self):
    self.queryDict = oracQry.treeDict
    self.treeDict.clear()
  
  def load(self, sFilePath):
    if self.dns_tns and self.pool:
      return
    
    judgementDBFD = open(sFilePath, "rt")
    print("[Judgement Load] File Path: {}".format(sFilePath), file=sys.stderr)
    
    while True:
      sBufIn = judgementDBFD.readline()
      if not sBufIn:
        judgementDBFD.close()
        break
      elif sBufIn[0] == '#' or sBufIn[0] == '\n':
        continue
      
      try:
        option, value = sBufIn.split()
      except ValueError:
        print("[Judgement Load] Wrong formated string: {}".format(sBufIn), file=sys.stderr)
        continue
      
      try:
        curValue = self.__dict__[option]
      except KeyError:
        print("[Judgement Load] There's no option [{}]".format(option), file=sys.stderr)
        continue
      else:
        pass
      
      if type(curValue) == int:
        value = int(value)
      
      if curValue != value:
        self.__dict__[option] = value
        print("[Judgement changed] {}: {} > {}".format(option, curValue, value), file=sys.stderr)

    
    print("[Judgement Load] Load Process Completed", file=sys.stderr)
    sys.stderr = self.config.applyLog(sys.stderr)
  
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
  def __init__(self, sFilePath, config):
    super().__init__()
    self.judgementTree = JudgementTree()
    self.sFilePath = sFilePath
    self.judgementTree.config = config
    
    self.judgementTree.init()
    try:
      self.judgementTree.load(self.sFilePath)
    except (FileNotFoundError,TypeError,OSError) as e:
      print("[Judgement Init] There's no DB Config File [{}]".format(sFilePath), file=sys.stderr)
      print(str(e))
      sys.exit(1)
    self.judgementTree.updateAll()
    
    self.updaterKillFlag = False
    self.updater = multiprocessing.Process(target=self.update, daemon=True)
    self.updater.start()
  
  def lookup(self, sURL):
    if self.judgementTree.lookup(sURL) < 0:
      return -1
    return 0
  
  def reviveUpdater(self):
    if not self.updater.is_alive():
      self.updater = multiprocessing.Process(target=self.update, daemon=True)
      self.updater.start()
  
  def update(self):
    sys.stderr = self.judgementTree.config.applyLog(sys.stderr)
    while True:
      time.sleep(self.judgementTree.DBUpdatePeriod)
      if self.updaterKillFlag:
        break
      
      try:
        self.judgementTree.load(self.sFilePath)
      except (FileNotFoundError,TypeError,OSError):
        print("[Judgement Update] There's no DB Config File [{}]".format(self.sFilePath), file=sys.stderr)
      except Exception as e:
        print(str(e), file=sys.stderr)
        
      self.judgementTree.updateAll()
      
      sys.stderr = self.judgementTree.config.applyLog(sys.stderr)
      
  def changeConfig(self, config):
    if config:
      self.judgementTree.config = config
  
  def changePath(self, sFilePath):
    self.sFilePath = sFilePath

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
