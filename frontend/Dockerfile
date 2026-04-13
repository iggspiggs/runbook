FROM node:20-alpine

WORKDIR /app

# Install dependencies first (layer-cached unless package files change)
COPY package.json package-lock.json* ./
RUN npm install

# Copy the full source (src/ will be overridden by the dev volume mount)
COPY . .

EXPOSE 5173

# --host 0.0.0.0 is required so the Vite server accepts connections from
# outside the container (the host machine and other containers).
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
