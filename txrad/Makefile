CC = g++ -fPIC -Wall -ansi `pkg-config --cflags libbitcoin` -I/usr/include/python2.7 

default:
	$(CC) -c tx_sentinel.cpp -o tx_sentinel.o
	$(CC) -shared -Wl,-soname,tx_sentinel.so tx_sentinel.o -lpython2.7 -lboost_python `pkg-config --libs libbitcoin` -lboost_thread -o tx_sentinel.so

