# Optional: containerized dashboard for local all-in-one runs.
# In production the dashboard is intended for Vercel.
FROM node:22-slim
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]
