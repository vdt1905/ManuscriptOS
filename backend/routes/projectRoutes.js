import express from 'express';
import mongoose from 'mongoose';
import {
    createProject,
    getUserProjects,
    getRecentProjects,
    getProjectById,
    uploadProjectFile,
    updateProjectFileContent,
    renameProject,
    deleteProject,
    renameProjectFile,
    deleteProjectFile,
    updateValidationReport,
    downloadDocx,
    uploadMiddleware
} from '../controllers/projectController.js';
import { protectRoute } from '../middleware/authMiddleware.js';

const router = express.Router();

// Apply auth middleware to all project routes
router.use(protectRoute);

// A malformed id makes Mongoose throw a CastError, which the controllers
// report as a 500; answer 404 up front instead (stale bookmarks, typos).
const rejectInvalidId = (req, res, next, value) =>
    mongoose.Types.ObjectId.isValid(value)
        ? next()
        : res.status(404).json({ error: 'Not found' });
router.param('id', rejectInvalidId);
router.param('fileId', rejectInvalidId);

router.post('/', createProject);
router.get('/', getUserProjects);
router.get('/recent', getRecentProjects);
router.get('/:id', getProjectById);
router.put('/:id', renameProject);
router.delete('/:id', deleteProject);

router.post('/:id/files', uploadMiddleware.single('file'), uploadProjectFile);
router.put('/:id/files/:fileId/rename', renameProjectFile);
router.put('/:id/files/:fileId', updateProjectFileContent);
router.post('/:id/files/:fileId/download-docx', downloadDocx);
router.put('/:id/files/:fileId/report', updateValidationReport);
router.delete('/:id/files/:fileId', deleteProjectFile);

export default router;
