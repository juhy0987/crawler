import multiprocessing

class ProcessMgr(object):
  def __init__ (self, maxVal=0):
    self.children = dict()
    self.psNum = [ False ] * maxVal
    self.maxVal = maxVal

  def addProcess(self, target, args):
    if len(self.children) == self.maxVal:
      return None

    id = self.getUnusedNum()
    if id < 0:
      return None
    args = (id, ) + args
    newProcess = multiprocessing.Process(name=str(id), target=target, args=args, daemon=True)
    
    if not newProcess:
      return None

    self.children[id] = newProcess
    newProcess.start()
    return id

  def getProcess(self, id):
    try:
      return self.children[id]
    except KeyError:
      return None
  
  def isProcessAlive(self, id):
    try:
      tmp = self.children[id]
    except KeyError:
      return 1
    else:
      pass
    
    return tmp.exitcode
  
  def delProcess(self, process):
    try:
      del(self.children[process])
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
