import multiprocessing
import multiprocessing.managers

class PipeMgr(multiprocessing.managers.Namespace):
  def __init__ (self, maxProcess=0):
    self.conn = dict()
    self.psNum = [ False ] * maxProcess
    self.maxProcess = maxProcess
  
  def addPipe(self):
    if len(self.conn) == self.maxProcess:
      return None

    id = self.getUnusedNum()
    if id < 0:
      return None
    srcConn, destConn = multiprocessing.Pipe()

    self.conn[id] = srcConn
    return (id, destConn)

  def getPipe(self, id):
    try:
      return self.conn[id]
    except KeyError:
      return None
  
  def delPipe(self, id):
    try:
      del(self.conn[id])
    except KeyError:
      pass
    else:
      self.psNum[id] = False
  
  def setUnusedNum(self, id):
    self.psNum[id] = False
  
  def getUnusedNum(self):
    if False in self.psNum:
      tmp = self.psNum.index(False)
      self.psNum[tmp] = True
      return tmp
    return -1