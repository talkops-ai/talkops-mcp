#!/bin/sh

if [ "$(lsof +c 0 -p 1 | grep -e "^argocd-mcp-server.*\\s1\\s.*\\sunix\\s.*socket$" | wc -l)" -ne "0" ]; then
  echo -n "$(lsof +c 0 -p 1 | grep -e "^argocd-mcp-server.*\\s1\\s.*\\sunix\\s.*socket$" | wc -l) argocd-mcp-server streams found";
  exit 0;
else
  echo -n "Zero argocd-mcp-server streams found";
  exit 1;
fi;

echo -n "Never should reach here";
exit 99;