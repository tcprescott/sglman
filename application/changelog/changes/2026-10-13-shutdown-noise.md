### Behind the scenes
- Restarting the app no longer files two or three errors in the error tracker
  every time. The requests a restart cuts off are still listed in the logs, so a
  restart that really does hang still shows which page held it up.
