import socket

host = socket.gethostbyname('192.168.1.10')
port = 8493
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
print(host)
s.connect((host, port))
s.sendall(b'm')
data = s.recv(1024)
s.close()
print('Received', repr(data))