module.exports = {
  apps: [
    {
      name: "viet-nam-stock",
      script: "./start.sh",
      interpreter: "/bin/bash",
      kill_timeout: 5000,
      treekill: true,
      autorestart: true,
      // instances: "max",  // hoặc số core: 4
      // exec_mode: "cluster", // bắt buộc để dùng cluster mode
    }
  ]
};