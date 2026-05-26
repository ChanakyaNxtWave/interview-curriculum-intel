import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import CoursesPage from './pages/CoursesPage';
import KpListPage from './pages/KpListPage';
import KpDetailPage from './pages/KpDetailPage';
import ContentDetailPage from './pages/ContentDetailPage';
import InterviewQuestionsPage from './pages/InterviewQuestionsPage';
import TheoryQuestionsPage from './pages/TheoryQuestionsPage';
import TheoryQuestionDetailPage from './pages/TheoryQuestionDetailPage';
import EvalDashboardPage from './pages/EvalDashboardPage';
import ReviewQueuePage from './pages/ReviewQueuePage';
import ReadingMaterialsPage from './pages/ReadingMaterialsPage';

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/courses" replace />} />
        <Route path="/courses" element={<CoursesPage />} />
        <Route path="/courses/:courseId" element={<KpListPage />} />
        <Route path="/courses/:courseId/kps/:kpId" element={<KpDetailPage />} />
        <Route path="/content/:contentId" element={<ContentDetailPage />} />
        <Route path="/interview-questions" element={<InterviewQuestionsPage />} />
        <Route path="/review" element={<ReviewQueuePage />} />
        <Route path="/courses/:courseId/reading-materials" element={<ReadingMaterialsPage />} />
        <Route path="/courses/:courseId/theory-questions" element={<TheoryQuestionsPage />} />
        <Route
          path="/courses/:courseId/theory-questions/:rowKey"
          element={<TheoryQuestionDetailPage />}
        />
        <Route path="/courses/:courseId/evals" element={<EvalDashboardPage />} />
        {/* Legacy redirects */}
        <Route
          path="/theory-questions"
          element={<Navigate to="/courses/programming_foundations/theory-questions" replace />}
        />
        <Route
          path="/theory/evals"
          element={<Navigate to="/courses/programming_foundations/evals" replace />}
        />
        <Route path="*" element={<Navigate to="/courses" replace />} />
      </Routes>
    </Layout>
  );
}
