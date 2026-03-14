import {
  useQuery,
  useMutation,
  type UseQueryOptions,
  type UseMutationOptions,
} from '@tanstack/react-query'
import { apiClient, ApiError } from '@/api/client.ts'

/**
 * Convenience hook for GET requests via react-query.
 * Automatically wires up the API client and passes the AbortSignal.
 */
export function useApiQuery<T>(
  queryKey: readonly unknown[],
  endpoint: string,
  options?: Omit<UseQueryOptions<T, ApiError>, 'queryKey' | 'queryFn'>,
) {
  return useQuery<T, ApiError>({
    queryKey,
    queryFn: ({ signal }) => apiClient.get<T>(endpoint, signal),
    ...options,
  })
}

/**
 * Convenience hook for POST/PUT/PATCH/DELETE mutations via react-query.
 */
export function useApiMutation<TData, TVariables = unknown>(
  method: 'post' | 'put' | 'patch' | 'delete',
  endpoint: string,
  options?: Omit<UseMutationOptions<TData, ApiError, TVariables>, 'mutationFn'>,
) {
  return useMutation<TData, ApiError, TVariables>({
    mutationFn: (variables) => {
      switch (method) {
        case 'post':
          return apiClient.post<TData>(endpoint, variables)
        case 'put':
          return apiClient.put<TData>(endpoint, variables)
        case 'patch':
          return apiClient.patch<TData>(endpoint, variables)
        case 'delete':
          return apiClient.delete<TData>(endpoint)
      }
    },
    ...options,
  })
}
