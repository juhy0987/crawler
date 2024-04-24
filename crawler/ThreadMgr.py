import threading

from Config import config

class ThreadMgr(object):
  def __init__(self, maxThreadVal=0):
    self.threads = dict()
    self.psNum = [ False ] * maxThreadVal
    self.maxThreadVal = maxThreadVal
    
  def addThread(self, target, args):
    if len(self.threads) == self.maxProcessVal:
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
      return 1
    else:
      pass
    
    return tmp.exitcode
  
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
