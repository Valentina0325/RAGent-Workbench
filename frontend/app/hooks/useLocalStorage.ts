import { useState, useEffect,Dispatch, SetStateAction } from 'react';

export function useLocalStorage<T>(key: string, initialValue: T): [T, Dispatch<SetStateAction<T>>] {
  // 获取初始值（优先从 localStorage 读，否则用 initialValue）
  const [storedValue, setStoredValue] = useState<T>(() => {
    if (typeof window === 'undefined') return initialValue;
    try {
      const item = window.localStorage.getItem(key);
      return item ? (JSON.parse(item) as T) : initialValue;
    } catch (error) {
      console.warn(`Error reading localStorage key “${key}”:`, error);
      return initialValue;
    }
  });

  // 封装 setter，同时更新 state 和 localStorage
 const setValue = (value: T | ((prev: T) => T)) => {
  try {
    const newValue = value instanceof Function ? value(storedValue) : value;
    setStoredValue(newValue);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(key, JSON.stringify(newValue));
    }
  } catch (error) {
    console.warn(`Error setting localStorage key “${key}”:`, error);
  }
};

  // 可选：监听其他标签页的 storage 事件（保持同步），如不需要可省略
  useEffect(() => {
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === key && e.newValue) {
        try {
          setStoredValue(JSON.parse(e.newValue));
        } catch {}
      }
    };
    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, [key]);

  return [storedValue, setValue];
}