// Fill out your copyright notice in the Description page of Project Settings.


#include "LFunctionLibrary.h"

FString ULFunctionLibrary::TimeStampAsString_Now()
{
	const int64&& TimeStamp = FDateTime::Now().ToUnixTimestamp();
	return FString::Printf(TEXT("%lld"), TimeStamp);
}


