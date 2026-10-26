import './config/env.js'; // must be first: loads .env before other imports read it
import express from 'express';
import cors from 'cors';
import mongoose from 'mongoose';

import { connectDB } from './db/connectDB.js';
import authRoutes from './routes/authRoutes.js';
import projectRoutes from './routes/projectRoutes.js';

const app = express();

app.use(cors());
app.use(express.json()); // allows us to parse incoming requests:req.body

// This service owns auth + projects only. The browser calls the FastAPI
// service (chatbot, deep-scan, file editor, toolkit — including LaTeX
// compilation via tectonic) directly on its own port.
app.use("/api/auth", authRoutes);
app.use("/api/projects", projectRoutes);

// Health checks for Docker / Kubernetes.
//   /healthz  liveness:  the process is up (a failure restarts the container)
//   /readyz   readiness: MongoDB is connected (a failure only stops traffic)
app.get('/healthz', (req, res) => res.json({ status: 'ok', service: 'auth-service' }));
app.get('/readyz', (req, res) => {
  const ready = mongoose.connection.readyState === 1;
  res.status(ready ? 200 : 503).json({ ready, db: ready ? 'connected' : 'not connected' });
});

const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
  connectDB();
  console.log(`Server is running on port ${PORT}`);
});