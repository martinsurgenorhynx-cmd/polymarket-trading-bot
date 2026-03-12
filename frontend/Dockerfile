# QuantDinger Frontend - Pre-built Static Files
# No build step needed - dist/ is already compiled.
FROM nginx:1.25-alpine

# Copy pre-built frontend files
COPY dist/ /usr/share/nginx/html/

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
