import multiprocessing

class ProcessMgr(object):
  def __init__ (self, maxProcess=0):
    self.children = dict()
    self.pipes = dict()
    self.psNum = [ False ] * maxProcess
    self.maxProcess = maxProcess

  def addProcess(self, target, args):
    if len(self.children) == self.maxProcess:
      return None

    id = self.getUnusedNum()
    if id < 0:
      return None
    
    parentConn, childConn = multiprocessing.Pipe()
    args = (id, childConn) + args
    newProcess = multiprocessing.Process(name=str(id), target=target, args=args, daemon=True)
    
    if not newProcess:
      return None

    self.children[id] = newProcess
    self.pipes[id] = parentConn
    newProcess.start()
    return id

  def getProcess(self, id):
    try:
      return self.children[id]
    except KeyError:
      return None
  
  def getPipe(self, id):
    try:
      return self.pipes[id]
    except KeyError:
      return None
  
  def isProcessAlive(self, id):
    try:
      tmp = self.children[id]
    except KeyError:
      return False
    else:
      pass
    
    return tmp.is_alive()
  
  def delProcess(self, id):
    try:
      del(self.children[id])
      del(self.pipes[id])
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

  def setMaxProcess(self, num):
    self.maxProcess = num