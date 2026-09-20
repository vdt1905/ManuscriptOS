import './config/env.js'; // must be first: loads .env before other imports read it
import express from 'express';
import cors from 'cors';

import { connectDB } from './db/connectDB.js';
import authRoutes from './routes/authRoutes.js';
import projectRoutes from './routes/projectRoutes.js';

const app = express();

app.use(cors());
app.use(express.json()); // allows us to parse incoming requests:req.body

// AI traffic (/api/ai/*) is routed to FastAPI by NGINX (see nginx/default.conf),
// not by Express — so this service only owns auth + projects. LaTeX compilation
// is handled by the Python backend (tectonic).
app.use("/api/auth", authRoutes);
app.use("/api/projects", projectRoutes);

const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
  connectDB();
  console.log(`Server is running on port ${PORT}`);
});