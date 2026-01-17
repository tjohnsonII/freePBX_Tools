#!/bin/bash

#ssh into the remote server
ssh tjohnson@192.168.50.1

#Enumerate sudo version
sudo -V

#Enumerate users
cat /etc/passwd | cut -d ":" -f 1

#Enumerate groups
cat /etc/group | cut -d ":" -f 1

#Enumerate Services
netstat -anlp
netstat -ano

#Enumerate root run bianries
ps aux | grep root

#Enumerate root Crontab
cat /etc/crontab | grep 'root'

#Enumerate binary version
program -v
program --version
program -V
dpkg -l | grep "program"

#Enumerate shells
cat /etc/shells

#Enumberate current shell
echo $SHELL 

#Enumberate Shell Version
/bin/bash --version

#Enumberate sudo rights
sudo -l

#Enumberate root Crontab
cat /etc/crontab | grep 'root'

#Enumerate SUID - SGID executables
find / -type f -a \( -perm -u+s -o -perm -g+s \) -exec ls -l {} \; 2> /dev/null

#Enumberate not-reseted Env Variables
sudo -l

#Enumberate Backups
find /var /etc /bin /sbin /home /usr/local/bin /usr/local/sbin /urs/bin /usr/games /usr/sbin /root /tmp -typ f \( -name "*backup*" -o -name *"\.back" -o -name "*\.bck" -o -name "*\.bk" \) 2>/dev/null

#Enumerate DBs
find / -name '.db' -o -name '.sqlite' -o -name '*.sqlite3' 2>/dev/null

#Enumberate Hidden Files
find / -type f -iname ".*" -ls 2>/dev/null

#Enumberate Programming Languages
which pythone
which perl
which ruby
which lua0
