import logging

class StreamToLogger(object):
  """
  Fake stream object that redirects writes to a logger instance
  """
  def __init__ (self, logger, level=logging.NOTSET):
    self.logger = logger
    self.level = level
    self.linebuf = ''
    
  def write(self, buf):
    for line in buf.rstrip().splitlines():
      self.logger.log(self.level, line.rstrip())
  
  def flush(self):
    pass

def setLogConfig(logger, config):
  for changed in config.changeList:
    match changed:
      case "LogLevel":
        setLoggerLevel(logger, config.LogLevel)
      case "LogFilePath":
        for handler in logger.handlers:
          handler.close()
          logger.removeHandler(handler)
        
        if config.LogFilePath == "":
          streamHandler = logging.StreamHandler()
          logger.addHandler(streamHandler)
        else:
          fileHandler = logging.FileHandler(config.LogFilePath)
          fileHandler.setFormatter(config.formatter)
          logger.addHandler(fileHandler)
      case _:
        pass

def setLoggerLevel(logger, logLevel=None):
  match logLevel:
    case 0:
      logger.setLevel(logging.NOTSET)
    case 1:
      logger.setLevel(logging.DEBUG)
    case 2:
      logger.setLevel(logging.INFO)
    case 3:
      logger.setLevel(logging.WARNING)
    case 4:
      logger.setLevel(logging.ERROR)
    case 5:
      logger.setLevel(logging.CRITICAL)
    case _:
      return False
  return True