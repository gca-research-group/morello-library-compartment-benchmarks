#include        <stdlib.h>
#include	<unistd.h>
#include        <stdio.h>
#include        <time.h>
#include        <assert.h>
#include        <string.h>

#define STRLEN     1024 
#define NUM_OF_MSG 100

#define MAX_MSG_SIZE 16384
static const int MSG_SIZES[] = {
    1024, 2048, 4096, 6144, 8192, 16384
};
static const int NUM_SIZES = (sizeof(MSG_SIZES) / sizeof(MSG_SIZES[0]));

/*
 source
 https://stackoverflow.com/questions/15767691/whats-the-c-library-function-to-generate-random-string
 */
void rand_str(char *dest, size_t length) {
    char charset[] = "0123456789"
                     "abcdefghijklmnopqrstuvwxyz"
                     "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

    while (length-- > 0) {
        size_t index = (double) rand() / RAND_MAX * (sizeof charset - 1);
        *dest++ = charset[index];
    }
    *dest = '\0';
}

int main()
{
    int pipechan[2], child;

    FILE *log_file = fopen("pipe-out-experiment-results.csv", "w");
    if (log_file == NULL) {
        printf("error: opening CSV file.\n");
        exit(1);
    }

    fprintf(log_file, "Test,Message Size (Bytes),Write Time (ms),Read Time (ms),Total Time (ms)\n");
    fclose(log_file); 

    if (pipe(pipechan)) {
        printf("error: opening stream sockets pair");
        exit(10);
    }

    if ((child = fork()) == -1) {
        printf("error: fork child1 failed"); 
        exit(-1);
    }

    if (child > 0) /* parent proc */
    {
        printf("I'm the PARENT process!\n"); 
        close(pipechan[1]);  
        
        char buf1[MAX_MSG_SIZE];
        struct timespec start_read, end_read;

        log_file = fopen("pipe-out-experiment-results.csv", "a");
        if (log_file == NULL) {
            printf("error: opening CSV file.\n");
            exit(1);
        }

        for (int s = 0; s < NUM_SIZES; s++) {
            int MSG_SIZE = MSG_SIZES[s];

            for (int i = 0; i < NUM_OF_MSG; i++) 
            {
                clock_gettime(CLOCK_MONOTONIC, &start_read);                
               
                if (read(pipechan[0], buf1, MSG_SIZE) < 0) 
                {
                    printf("error: reading from pipe failed!!!");
                    exit(-1);
                }

                clock_gettime(CLOCK_MONOTONIC, &end_read);
                
                double read_time = ((end_read.tv_sec - start_read.tv_sec) * 1000.0) +
                                   ((end_read.tv_nsec - start_read.tv_nsec) / 1e6);

                double write_time;
                if (read(pipechan[0], &write_time, sizeof(double)) < 0) {
                    printf("error: reading write time from pipe failed!!!");
                    exit(-1);
                }
                
                double total_time = write_time + read_time;
                
                fprintf(log_file, "%d,%d,%.3f,%.3f,%.3f\n", i + 1, MSG_SIZE, write_time, read_time, total_time);
                
                printf("i= %d", i);
                printf("\n\n\n!!!!!!!!msg recv from child proc %s : \n", buf1);
                printf("\n\n\n");
            }
        }

        fclose(log_file);  

    } else /* child proc */
    {
        printf("I'm the CHILD process!\n"); 
        close(pipechan[0]);
        struct timespec start_write, end_write;

        for (int s = 0; s < NUM_SIZES; s++) {
            int MSG_SIZE = MSG_SIZES[s];

            for (int k = 0; k < NUM_OF_MSG; k++) 
            {                 
                char *str = (char *) malloc(MSG_SIZE);
                if (!str) { printf("error: malloc child\n"); exit(1); }
                
                str[MSG_SIZE-1] = '\1';
                rand_str(str, MSG_SIZE-1);
                
                clock_gettime(CLOCK_MONOTONIC, &start_write);
                
                if (write(pipechan[1], str, MSG_SIZE) < 0) 
                {
                    printf("error: writing to pipe failed!!!");
                    exit(-1);
                }

                clock_gettime(CLOCK_MONOTONIC, &end_write);
                
                double write_time = ((end_write.tv_sec - start_write.tv_sec) * 1000.0) +
                                    ((end_write.tv_nsec - start_write.tv_nsec) / 1e6);
                
                if (write(pipechan[1], &write_time, sizeof(double)) < 0) {
                    printf("error: writing write time to pipe failed!!!");
                    exit(-1);
                }
                free(str);
            }
        }
    }
}
