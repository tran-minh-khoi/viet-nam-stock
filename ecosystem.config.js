module.exports = {
  apps: [
    {
      name: "citizen-stock",
      script: "./start.sh",
      interpreter: "/bin/bash",
      // instances: "max",  // hoặc số core: 4
      // exec_mode: "cluster", // bắt buộc để dùng cluster mode
    }
  ]
};