module.exports = {
  apps: [
    {
      name: "viet-nam-stock",
      script: "./start.sh",
      interpreter: "/bin/bash",
      kill_timeout: 5000,
      autorestart: true,
    },
  ],
};
