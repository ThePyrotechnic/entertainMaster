import socket

host = socket.gethostbyname('192.168.1.8')
port = 8493
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
print(host)
s.connect((host, port))
s.sendall(b'v03f0203,f0206,f0811')
data = s.recv(1024)
s.close()
print('Received', repr(data))