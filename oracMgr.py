import sys
import pickle
import cx_Oracle

CONFIG_PATH = "./config/oracdb.conf"

def main():
  config = dict()
  fd = open(CONFIG_PATH, "rt")
  
  while True:
    sBufIn = fd.readline()
    if not sBufIn:
      fd.close()
      break
    elif sBufIn[0] == '#' or sBufIn[0] == '\n':
      continue
    
    try:
      option, value = sBufIn.split()
    except ValueError:
      print("[Judgement Load] Wrong formated string: {}".format(sBufIn), file=sys.stderr)
      continue
    
    config[option] = value
  config["Port"] = int(config["Port"])
  qry = sys.stdin.read()
  
  # qry = "SELECT filter_string FROM TBL_FILTER_SETUP WHERE filter_type='FT003'"
  print(qry, file=sys.stderr)
  conts = []
  try:
    dsn_tns = cx_Oracle.makedsn(config["HostIP"], config["Port"], config["Sid"])
    conn = cx_Oracle.connect(config["ID"], config["Password"], dsn_tns)
    
    cur = conn.cursor()
    cur.execute(qry)
    conts = cur.fetchall()
    # print("[Judgement Load] DB Access Success", file=sys.stderr)
  except cx_Oracle.DatabaseError as e:
    # print("[Judgement Load] DB Access Failed", file=sys.stderr)
    conts = []
    # raise e
  finally:
    try:
      cur.close()
    except:
      pass
    try:
      conn.close()
    except:
      pass
  
  # print(conts)
  data = pickle.dumps(conts)
  sys.stdout.buffer.write(data)
    
    
if __name__=="__main__":
  main()