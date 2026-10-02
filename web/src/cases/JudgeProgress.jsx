import { Alert } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';
import { judgeProgress } from './judgeProgress.js';

export default function JudgeProgress({ item }) {
  const progress = judgeProgress(item);
  return progress ? <Alert type="info" showIcon icon={<LoadingOutlined spin />}
    message={progress.title} description={progress.description} /> : null;
}
