# Traceroute Visualizer – Quick Start (Windows + FreeBSD)

This app visualizes traceroute paths collected from a remote FreeBSD host and renders the route and map in a Next.js UI.

## 1) Start the backend on FreeBSD

Run the Python 2 HTTP server (supports `/health`, ICMP/TCP, partial results):

```sh
/usr/local/bin/python /usr/home/tjohnson/traceroute_server.py
# or keep running in background
nohup /usr/local/bin/python /usr/home/tjohnson/traceroute_server.py \
	>/usr/home/tjohnson/traceroute_server.log 2>&1 &
```

Quick checks on the FreeBSD host:

```sh
sockstat -4l | grep 8000
fetch -o - "http://localhost:8000/health"
fetch -o - "http://localhost:8000/?target=8.8.8.8&mode=icmp"
```

If TCP 8000 is blocked from Windows, either open the port (IPFW/PF) or use an SSH tunnel:

```sh
ssh -o HostKeyAlgorithms=+ssh-dss -o PubkeyAcceptedAlgorithms=+ssh-dss \
		-L 8000:localhost:8000 tjohnson@192.168.50.1
```

## 2) Configure the frontend on Windows (E:\)

Create/edit `.env.local` in the app folder to point at the backend:

```powershell
Push-Location "E:\DevTools\freepbx-tools\traceroute-visualizer-main\traceroute-visualizer-main"
(Get-Content .env.local) -replace 'BACKEND_URL=.*','BACKEND_URL=http://192.168.50.1:8000' | Set-Content .env.local
# If using SSH tunnel, instead use 127.0.0.1
(Get-Content .env.local) -replace 'BACKEND_URL=.*','BACKEND_URL=http://127.0.0.1:8000' | Set-Content .env.local
Pop-Location
```

## 3) Run the Next.js UI

```powershell
Push-Location "E:\DevTools\freepbx-tools\traceroute-visualizer-main\traceroute-visualizer-main"
npm.cmd install
npm.cmd run dev
```

Open http://localhost:3000 and:
- Choose the Probe (ICMP recommended)
- Enter a target (e.g., `192.168.50.24`, `8.8.8.8`)
- View the hop cards and map

Quick health from Windows:

```powershell
curl.exe -s "http://localhost:3000/api/health"
curl.exe -s -X POST -H "Content-Type: application/json" -d "{\"target\":\"8.8.8.8\",\"mode\":\"icmp\"}" "http://localhost:3000/api/traceroute"
```

---

This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
