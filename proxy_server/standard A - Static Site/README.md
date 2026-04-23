For 123hostedtools.com the baseline is now:

port 80 vhost present

redirects to HTTPS

docroot: /var/www/123hostedtools.com/public

port 443 vhost present

LE cert path unchanged

logs unchanged

headers module enabled

response headers:

X-Content-Type-Options: nosniff

X-Frame-Options: SAMEORIGIN

Referrer-Policy: strict-origin-when-cross-origin

That is worth writing down because this becomes your repeatable pattern.