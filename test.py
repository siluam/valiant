from subprocess import Popen, PIPE
Popen("nix eval --show-trace --impure --expr '(import /home/shadowrylander/shadowrylander/sylveon/sylvorg.github.io).pname'", shell = True, stdout = PIPE, stderr = PIPE, bufsize = 0).wait()
