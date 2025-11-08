SELECT s.company_name, COUNT(d.id) as phone_count
FROM sites s
JOIN devices d ON s.site_id = d.site_id
WHERE d.vendor = 'yealink'
GROUP BY s.company_name
ORDER BY phone_count DESC;